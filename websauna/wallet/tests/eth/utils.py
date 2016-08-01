from typing import Tuple

from decimal import Decimal
from uuid import UUID

import pytest
import time
import transaction
from eth_rpc_client import Client

from web3 import Web3
from web3.contract import Contract

from populus.utils.transactions import wait_for_transaction_receipt
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.ethereum.service import EthereumService


# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.models import CryptoOperation

GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


NETWORK_PARAMETERS = {
    "local_geth": {
        "withdrawal_fee": Decimal(0)
    },

    "testnet": {
        "withdrawal_fee": WITHDRAWAL_FEE
    }
}

def wait_tx(web3: Web3, txid: str):
    return wait_for_transaction_receipt(web3, txid, 60)


def create_contract_listener(contract: Contract) -> Tuple[ContractListener, list]:
    """Get a listener which pushes incoming events of one contract to a list object."""

    assert isinstance(contract, Contract)
    contract_events = []

    web3 = contract.web3

    def cb(wallet_contract_address, event_name, event_data, log_entry):
        contract_events.append((event_name, event_data))
        return True  # increase updates with 1

    current_block = web3.eth.blockNumber

    listener = create_populus_listener(web3, cb, contract.__class__, from_block=current_block)
    listener.monitor_contract(contract.address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    listener.poll()
    contract_events[:] = []

    return listener, contract_events


def get_withdrawal_fee(web3: Web3) -> Decimal:
    """How much gas HostedWallet withdraw() operation should cost."""

    # Some broken abstraction here - assume test web3 instance
    # tells us more about the network implicitly
    mode = getattr(web3, "mode", "local_geth")
    return NETWORK_PARAMETERS[mode]["withdrawal_fee"]


def wait_for_op_confirmations(eth_service: EthereumService, opid: UUID):
    """Wait that an op reaches required level of confirmations."""

    with transaction.manager:
        op = eth_service.dbsession.query(CryptoOperation).get(opid)
        if op.confirmed_at:
            pytest.fail("Already confirmed")

        assert op.required_confirmation_count

    # Wait until the transaction confirms (1 confirmations)
    deadline = time.time() + 47
    while time.time() < deadline:
        success_op_count, failed_op_count = eth_service.run_event_cycle()
        if success_op_count > 0:

            # Check our op went through
            with transaction.manager:
                op = eth_service.dbsession.query(CryptoOperation).get(opid)
                if op.confirmed_at:
                    break

        if failed_op_count > 0:
            pytest.fail("Faiures within confirmation wait should not happen")
        time.sleep(1)

    if time.time() > deadline:
        pytest.fail("Did not receive confirmation updates")


def send_balance_to_contract(contract: Contract, value: Decimal) -> str:
    """Send balance from geth coinbase to the contract.

    :param contract: Contract instance with an address

    :param value: How much to send

    :return: Transaction hash of the send operation
    """
    web3 = contract.web3
    tx = {
        "from": web3.eth.coinbase,
        "to": contract.address,
        "value": to_wei(value)
    }
    return web3.eth.sendTransaction(tx)


def send_balance_to_address(web3: Web3, address: str, value: Decimal) -> str:
    assert address.startswith("0x")
    tx = {
        "from": web3.eth.coinbase,
        "to": address,
        "value": to_wei(value)
    }
    return web3.eth.sendTransaction(tx)