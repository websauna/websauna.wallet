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
from websauna.wallet.ethereum.asset import get_house_address
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.ethereum.service import EthereumService


# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import Asset
from websauna.wallet.models import AssetClass
from websauna.wallet.models import CryptoAddress

from websauna.wallet.ethereum.confirm import wait_for_op_confirmations

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


def create_token_asset(dbsession, eth_service, eth_network_id, name, symbol, supply) -> UUID:
    """Create a token in the network and assigns it to coinbase address."""

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = network.create_asset(name=name, symbol=symbol, supply=Decimal(10000), asset_class=AssetClass.token)
        address = get_house_address(network)
        op = address.create_token(asset)
        opid = op.id
        aid = asset.id

    # This gives op a txid
    success, fails = eth_service.run_waiting_operations()
    assert success == 1

    wait_for_op_confirmations(eth_service, opid)
    return aid