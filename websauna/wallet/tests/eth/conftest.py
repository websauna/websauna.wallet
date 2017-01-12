import os


import pytest
from decimal import Decimal

import transaction
from populus.project import Project
from populus.utils.config import Config
from web3 import Web3, RPCProvider

from websauna.wallet.ethereum.asset import get_eth_network, get_ether_asset
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached
from websauna.wallet.ethereum.contract import Contract, deploy_contract
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.wallet import HostedWallet

from websauna.wallet.tests.eth.utils import wait_tx, send_balance_to_contract

#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


#: How much funds we put to test w  allet for withdrawal tests
TOP_UP_VALUE = Decimal("0.03")


TOYBOX_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"


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



@pytest.yield_fixture(scope="session")
def web3() -> Web3:
    """A py.test fixture to get a Web3 interface to a temporary geth instance.

    This is session scoped fixture.
    Geth is launched only once during the beginning of the test run.

    Geth will have huge instant balance on its coinbase account.
    Geth will also mine our transactions on artificially
    low difficulty level.

    :yield: :py:class:`web3.Web3` instance
    """

    project = Project()

    # Project is configured using populus.config.Config class
    # which is a subclass of Python config parser.
    # Instead of reading .ini file, here we dynamically
    # construct the configuration.
    project.config = Config()

    # Settings come for [populus] section of the config.
    project.config.add_section("populus")

    # Configure where Populus can find our contracts.json
    build_dir = os.path.join(os.getcwd(), "websauna", "wallet", "ethereum")
    project.config.set("populus", "build_dir", build_dir)

    chain_kwargs = {

        # Force RPC provider instead of default IPC one
        "provider": RPCProvider,
        "wait_for_dag_timeout": 20*60,
        "verbosity": "1",
        "overrides": {
            "jitvm": "false",
        }
    }

    # This returns
    with project.get_chain("temp", **chain_kwargs) as geth_proc:

        web3 = geth_proc.web3

        # Use compatible web3.py version
        assert web3._requestManager.provider.network_timeout

        web3._requestManager.provider.network_timeout = 10
        web3._requestManager.provider.connection_timeout = 10

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

    return HostedWallet.create(web3, contract_name="Wallet2")


@pytest.fixture(scope="module")
def topped_up_hosted_wallet(web3, hosted_wallet):
    """Wallet with ensured amount of funds."""

    txid = send_balance_to_contract(hosted_wallet, TOP_UP_VALUE)
    wait_tx(web3, txid)
    return hosted_wallet


@pytest.fixture(scope="module")
def simple_test_contract(web3) -> Contract:
    """Create a contract where we can set a global variable for testing."""

    contract_def = get_compiled_contract_cached("TestContract")
    contract, txid = deploy_contract(web3, contract_def)
    return contract


@pytest.fixture(scope="module")
def decode_data_contract(web3) -> Contract:
    """Create a contract where we can set a global variable for testing."""

    contract_def = get_compiled_contract_cached("DecodeData")
    contract, txid = deploy_contract(web3, contract_def)
    return contract


@pytest.fixture(scope="module")
def token(web3, coinbase) -> Contract:
    """Deploy a token contract in the blockchain."""
    return Token.create_token(web3, name="Mootoken", supply=10000, symbol="MOO", owner=coinbase)


@pytest.fixture(scope="module")
def token(web3, coinbase) -> Contract:
    """Deploy a token contract in the blockchain."""
    return Token.create_token(web3, name="Mootoken", supply=10000, symbol="MOO", owner=coinbase)


@pytest.fixture
def eth_network_id(dbsession):
    """Get id for Ethereum primary AssetNetwork."""
    with transaction.manager:
        network = get_eth_network(dbsession)
        # Used by create_address op in MockEthereumService
        network.other_data["test_address_pool"] = [
            "0x2f70d3d26829e412a602e83fe8eebf80255aeea5",
            "0x5589C14FbC92A73809fBCfF33Ab40eFc7E8E8467",
            "0x7bd2f95cefada49141a7f467f40c42f94e3c7338"
        ]

        network.other_data["test_txid_pool"] = [
            "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf",
            "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dce",
            "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcd",
            "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcc",
            "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcb",
        ]

        return network.id


@pytest.fixture
def eth_asset_id(dbsession):
    with transaction.manager:
        asset = get_ether_asset(dbsession)
        dbsession.flush()
        return asset.id


@pytest.fixture
def testnet_network_id(dbsession):
    """Get id for Ethereum test AssetNetwork."""

    asset_network_name = "testnet"

    with transaction.manager:
        network = get_eth_network(dbsession, asset_network_name)
        return network.id






