"""Test wallet contract events. """
from typing import Tuple

import binascii
import pytest
from decimal import Decimal

from eth_rpc_client import Client

from populus.contracts.utils import deploy_contract
from populus.ethtester_client import EthTesterClient
from populus.utils import get_contract_address_from_txn
from shareregistry.utils import txid_to_bin, eth_address_to_bin
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.ethjsonrpc import EthJsonRpc
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.ethereum.wallet import create_wallet, send_coinbase_eth, get_wallet_balance, withdraw_from_wallet, get_wallet_contract_class

# How many ETH we move for test transactiosn
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.tests.integration.utils import wait_tx

TEST_VALUE = Decimal("0.0001")

# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


@pytest.fixture
def contract_address(client: Client, geth_node, geth_coinbase: str) -> str:
    """Deploy a smart contract to local private blockchain so test functions can stress it out.

    :param client: py.test fixture to create RPC client to call geth node

    :param geth_node: py.test fixture to spin up geth node with test network parameters

    :param geth_coinbase: Ethereum account number for coinbase account where our mined ETHs appear

    :return: 0x prefixed hexadecimal address of the deployed contract
    """

    # Make sure that we have at least one block mined
    client.wait_for_block(1)

    print("Value ", client.get_balance(geth_coinbase))

    # Make sure we have some ETH on coinbase account
    # so that we can deploy a contract
    assert client.get_balance(geth_coinbase) > 0

    # We define the Populus Contract class outside the scope
    # of this example. It would come from compiled .sol
    # file loaded through Populus framework contract
    # mechanism.
    contract = get_wallet_contract_class()

    # Get a transaction hash where our contract is deployed.
    # We set gas to very high randomish value, to make sure we don't
    # run out of gas when deploying the contract.
    deploy_txn_hash = deploy_contract(client, contract, gas=1500000)

    # Wait that the geth mines a block with the deployment
    # transaction
    client.wait_for_transaction(deploy_txn_hash)

    contract_addr = get_contract_address_from_txn(client, deploy_txn_hash)

    return contract_addr


@pytest.fixture
def client(rpc_client):
    return rpc_client


def create_contract_listener(client: EthJsonRpc, contract_address) -> Tuple[ContractListener, list]:
    """Get a listener which pushes incoming events to a list object."""
    contract_events = []

    def cb(contract_address, event_name, event_data, log_entry):
        contract_events.append((event_name, event_data))
        return True  # increase updates with 1

    current_block = client.get_block_number()

    listener = create_populus_listener(client, cb, get_wallet_contract_class(), from_block=current_block)
    listener.monitor_contract(contract_address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    listener.poll()
    contract_events[:] = []

    return listener, contract_events


@pytest.mark.slow
def test_event_fund_wallet(client, contract_address):
    """Send some funds int the wallet and see that we get the event of the deposit."""

    listener, events = create_contract_listener(client, contract_address)

    # value = get_wallet_balance(testnet_contract_address)
    txid = send_coinbase_eth(client, TEST_VALUE, contract_address)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)

    # Deposit some more, should generate one new event
    txid = send_coinbase_eth(client, TEST_VALUE, contract_address)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 2
    event_name, input_data = events[1]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)

