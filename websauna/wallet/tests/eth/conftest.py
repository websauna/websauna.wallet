import os
from uuid import UUID

import pytest
from decimal import Decimal

import transaction
from eth_rpc_client import Client
from web3 import Web3, RPCProvider
from populus.chain import testing_geth_process


from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached
from websauna.wallet.ethereum.contract import Contract, deploy_contract
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models.account import AssetClass

from websauna.wallet.tests.eth.utils import wait_tx, send_balance_to_contract

#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


#: How much funds we put to test w  allet for withdrawal tests
TOP_UP_VALUE = Decimal("0.03")


@pytest.fixture(scope="session")
def client_mode():
    """We run either against public testnet or our internal geth node."""
    client_mode = os.environ.get("ETHEREUM_MODE")
    if client_mode == "testnet":
        return "testnet"
    else:
        return "local_geth"


@pytest.fixture(scope="session")
def client_credentials(registry) -> tuple:
    """Return password and unlock seconds needed to unlock the client."""

    password = registry.settings.get("ethereum.ethjsonrpc.unlock_password", "")
    unlock_seconds = int(registry.settings.get("ethereum.ethjsonrpc.unlock_seconds", 24 * 3600))
    return password, unlock_seconds


@pytest.fixture(scope="session")
def client(request, client_mode, client_credentials) -> Web3:
    pass


@pytest.yield_fixture(scope="session")
def web3(request, client_mode, client_credentials) -> Web3:
    """A py.test fixture to get a Web3 interface to locally launched geth.

    This is session scoped fixture.
    Geth is launched only once during the beginning of the test run.

    Geth will have huge instant balance on its coinbase account.
    Geth will also mine our transactions on artificially
    low difficulty level.
    """

    # Ramp up a local geth server, store blockchain files in the
    # current working directory
    with testing_geth_process(project_dir=os.getcwd(), test_name="test") as geth_proc:
        # Launched in port 8080
        web3 = Web3(RPCProvider(host="127.0.0.1", port=geth_proc.rpc_port))

        # Allow access to sendTransaction() to use coinbase balance
        # to deploy contracts. Password is from py-geth
        # default_blockchain_password file. Assume we don't
        # run tests for more than 9999 seconds
        coinbase = web3.eth.coinbase
        success = web3.personal.unlockAccount(
            coinbase,
            passphrase="this-is-not-a-secure-password",
            duration=9999)

        assert success, "Could not unlock test geth coinbase account"

        yield web3


@pytest.fixture(scope="session")
def coinbase(web3) -> str:
    """Get coinbase address of locally running geth."""
    return web3.eth.coinbase


@pytest.fixture(scope="module")
def hosted_wallet(web3: Web3, coinbase: str) -> HostedWallet:
    """Deploy a smart contract to local private blockchain so test functions can stress it out.

    :param client: py.test fixture to create RPC client to call geth node

    :param geth_node: py.test fixture to spin up geth node with test network parameters

    :param coinbase: Ethereum account number for coinbase account where our mined ETHs appear

    :return: 0x prefixed hexadecimal address of the deployed contract
    """

    return HostedWallet.create(web3)


@pytest.fixture(scope="module")
def topped_up_hosted_wallet(web3, hosted_wallet):
    """Wallet with ensured amount of funds."""

    txid = send_balance_to_contract(hosted_wallet, TOP_UP_VALUE)
    wait_tx(web3, txid)
    return hosted_wallet


@pytest.fixture(scope="module")
def simple_test_contract(web3) -> Contract:
    """Create a contract where we can set a global variable for testing."""

    contract_def= get_compiled_contract_cached("TestContract")
    contract, txid = deploy_contract(web3, contract_def)
    return contract


@pytest.fixture(scope="module")
def token(client, coinbase) -> Contract:
    """Deploy a token contract in the blockchain."""
    return Token.create(client, name="Mootoken", supply=10000, symbol="MOO", owner=coinbase)


@pytest.fixture
def eth_network_id(dbsession):
    """Get id for Ethereum primary AssetNetwork."""
    with transaction.manager:
        network = get_eth_network(dbsession)
        return network.id


@pytest.fixture
def testnet_network_id(dbsession):
    """Get id for Ethereum test AssetNetwork."""

    asset_network_name = "testnet"

    with transaction.manager:
        network = get_eth_network(dbsession, asset_network_name)
        return network.id




