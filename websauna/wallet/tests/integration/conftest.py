import os

import pytest
from decimal import Decimal
from eth_rpc_client import Client

from populus.contracts import Contract
from populus.contracts.core import ContractBase
from populus.plugin import geth_node, geth_node_command
from websauna.wallet.ethereum.populuscontract import get_compiled_contract_cached
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.ethereum.wallet import send_coinbase_eth, HostedWallet

from websauna.wallet.tests.integration.utils import wait_tx, deploy_wallet, deploy_contract_tx

#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


#: How much funds we put to test w  allet for withdrawal tests
TOP_UP_VALUE = Decimal("0.0003")


@pytest.fixture(scope="module")
def client_mode():
    """We run either against public testnet or our internal geth node."""
    client_mode = os.environ.get("ETHEREUM_MODE")
    if client_mode == "testnet":
        return "testnet"
    else:
        return "local_geth"


@pytest.fixture(scope="module")
def client(request, client_mode, populus_config) -> Client:
    """Create a RPC client.

    This either points to a geth running in public testnet or we will spin up a new local instance.
    """

    from eth_rpc_client import Client

    if client_mode == "local_geth":
        cmd = geth_node_command(request, populus_config)
        geth_node(request, cmd)
        rpc_port = populus_config.get_value(request, 'rpc_client_port')
        rpc_hostname = populus_config.get_value(request, 'rpc_client_host')
        client = Client(rpc_hostname, rpc_port)
        return client
    else:
        rpc_port = populus_config.get_value(request, 'rpc_client_port')
        rpc_hostname = populus_config.get_value(request, 'rpc_client_host')
        client = Client(rpc_hostname, rpc_port)
        return client


@pytest.fixture(scope="module")
def coinbase(client):
    return client.get_coinbase()


@pytest.fixture(scope="module")
def hosted_wallet(client: Client, geth_node, coinbase: str) -> HostedWallet:
    """Deploy a smart contract to local private blockchain so test functions can stress it out.

    :param client: py.test fixture to create RPC client to call geth node

    :param geth_node: py.test fixture to spin up geth node with test network parameters

    :param coinbase: Ethereum account number for coinbase account where our mined ETHs appear

    :return: 0x prefixed hexadecimal address of the deployed contract
    """

    return HostedWallet.create(client)


@pytest.fixture(scope="module")
def topped_up_hosted_wallet(client, coinbase, hosted_wallet):
    """Wallet with ensured amount of funds."""

    txid = client.send_transaction(_from=coinbase, to=hosted_wallet.address, value=to_wei(TOP_UP_VALUE))
    wait_tx(client, txid)
    return hosted_wallet


@pytest.fixture(scope="module")
def simple_test_contract(client, geth_node, coinbase) -> ContractBase:
    """Create a contract where we can set a global variable for testing."""

    contract_meta = get_compiled_contract_cached("testcontract.sol", "TestContract")
    contract_class = Contract(contract_meta, "TestContract")
    address = deploy_contract_tx(client, geth_node, coinbase, contract_class)
    return contract_class(address, client)
