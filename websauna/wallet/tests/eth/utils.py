from typing import Tuple

from decimal import Decimal
from uuid import UUID

import pytest
import time
import transaction
from eth_rpc_client import Client

from websauna.wallet.ethereum.contract import Contract
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.wallet import get_wallet_contract_class



# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
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

def wait_tx(eth_json_rpc, txid):
    try:
        eth_json_rpc.wait_for_transaction(txid, max_wait=90.0)
    except ValueError as e:
        raise ValueError("Could not broadcast transaction {}".format(txid)) from e


def deploy_contract_tx(client, geth_node, geth_coinbase, contract: type, constructor_args=None) -> str:
    """Deploy a contract.

    :return: Deployed contract address
    """

    # Make sure that we have at least one block mined
    client.wait_for_block(1)

    # Make sure we have some ETH on coinbase account
    # so that we can deploy a contract
    assert client.get_balance(geth_coinbase) > 0

    # Get a transaction hash where our contract is deployed.
    # We set gas to very high randomish value, to make sure we don't
    # run out of gas when deploying the contract.
    deploy_txn_hash = deploy_contract(client, contract, gas=1500000, constructor_args=constructor_args)

    # Wait that the geth mines a block with the deployment
    # transaction
    client.wait_for_transaction(deploy_txn_hash)

    contract_addr = get_contract_address_from_txn(client, deploy_txn_hash)

    return contract_addr


def deploy_wallet(client, geth_node, get_coinbase):
    # We define the Populus Contract class outside the scope
    # of this example. It would come from compiled .sol
    # file loaded through Populus framework contract
    # mechanism.
    contract = get_wallet_contract_class()
    return deploy_contract_tx(client, geth_node, get_coinbase, contract)


def create_contract_listener(contract: Contract) -> Tuple[ContractListener, list]:
    """Get a listener which pushes incoming events to a list object."""
    contract_events = []

    client = contract._meta.blockchain_client

    def cb(wallet_contract_address, event_name, event_data, log_entry):
        contract_events.append((event_name, event_data))
        return True  # increase updates with 1

    current_block = client.get_block_number()

    listener = create_populus_listener(client, cb, contract.__class__, from_block=current_block)
    listener.monitor_contract(contract._meta.address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    listener.poll()
    contract_events[:] = []

    return listener, contract_events


def get_withdrawal_fee(client: Client) -> Decimal:
    """How much gas HostedWallet withdraw() operation should cost."""
    mode = client.mode
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