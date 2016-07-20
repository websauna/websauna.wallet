import pytest
from decimal import Decimal
from eth_rpc_client import Client

from populus.contracts import Contract
from populus.contracts.core import ContractBase
from websauna.wallet.ethereum.populuscontract import get_compiled_contract_cached
from websauna.wallet.ethereum.wallet import send_coinbase_eth

from websauna.wallet.tests.integration.utils import wait_tx, deploy_wallet, deploy_contract_tx

#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


#: How much funds we put to test w  allet for withdrawal tests
TOP_UP_VALUE = Decimal("0.0003")


@pytest.fixture(scope="module")
def client(request, geth_node, populus_config):
    from eth_rpc_client import Client
    rpc_port = populus_config.get_value(request, 'rpc_client_port')
    rpc_hostname = populus_config.get_value(request, 'rpc_client_host')
    client = Client(rpc_hostname, rpc_port)
    return client


@pytest.fixture(scope="module")
def wallet_contract_address(client: Client, geth_node, geth_coinbase: str) -> str:
    """Deploy a smart contract to local private blockchain so test functions can stress it out.

    :param client: py.test fixture to create RPC client to call geth node

    :param geth_node: py.test fixture to spin up geth node with test network parameters

    :param geth_coinbase: Ethereum account number for coinbase account where our mined ETHs appear

    :return: 0x prefixed hexadecimal address of the deployed contract
    """

    return deploy_wallet(client, geth_node, geth_coinbase)


@pytest.fixture(scope="module")
def topped_up_wallet_contract_address(client, wallet_contract_address):
    """Wallet with ensured amount of funds."""

    txid = send_coinbase_eth(client, TOP_UP_VALUE, wallet_contract_address)
    wait_tx(client, txid)
    return wallet_contract_address


@pytest.fixture(scope="module")
def simple_test_contract(client, geth_node, geth_coinbase) -> ContractBase:
    """Create a contract where we can set a global variable for testing."""

    contract_meta = get_compiled_contract_cached("testcontract.sol", "TestContract")
    contract_class = Contract(contract_meta, "TestContract")
    address = deploy_contract_tx(client, geth_node, geth_coinbase, contract_class)
    return contract_class(address, client)
