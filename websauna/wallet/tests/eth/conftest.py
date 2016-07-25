import os
from uuid import UUID

import pytest
from decimal import Decimal

import transaction
from eth_rpc_client import Client

from populus.contracts import Contract
from populus.contracts.core import ContractBase
from populus.plugin import geth_node, geth_node_command, _start_geth_node
from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.populuscontract import get_compiled_contract_cached
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.ethereum.wallet import send_coinbase_eth, HostedWallet
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models.account import AssetClass

from websauna.wallet.tests.eth.utils import wait_tx, deploy_wallet, deploy_contract_tx

#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


#: How much funds we put to test w  allet for withdrawal tests
TOP_UP_VALUE = Decimal("0.03")


@pytest.fixture(scope="module")
def client_mode():
    """We run either against public testnet or our internal geth node."""
    client_mode = os.environ.get("ETHEREUM_MODE")
    if client_mode == "testnet":
        return "testnet"
    else:
        return "local_geth"


@pytest.fixture(scope="module")
def client_credentials(registry) -> tuple:
    """Return password and unlock seconds needed to unlock the client."""

    password = registry.settings.get("ethereum.ethjsonrpc.unlock_password", "")
    unlock_seconds = int(registry.settings.get("ethereum.ethjsonrpc.unlock_seconds", 24 * 3600))
    return password, unlock_seconds


@pytest.fixture(scope="module")
def client(request, client_mode, client_credentials, populus_config) -> Client:
    """Create a RPC client.

    This either points to a geth running in public testnet or we will spin up a new local instance.
    """

    from eth_rpc_client import Client

    if client_mode == "local_geth":
        cmd = geth_node_command(request, populus_config)
        proc = _start_geth_node(request, populus_config, cmd)
        rpc_port = populus_config.get_value(request, 'rpc_client_port')
        rpc_hostname = populus_config.get_value(request, 'rpc_client_host')
        client = Client(rpc_hostname, rpc_port)

        def kill_it():
            from populus.utils import (
                kill_proc,
            )
            kill_proc(proc)

        request.addfinalizer(kill_it)

    else:
        rpc_port = populus_config.get_value(request, 'rpc_client_port')
        rpc_hostname = populus_config.get_value(request, 'rpc_client_host')
        client = Client(rpc_hostname, rpc_port)

        # We need to unlock to allow withdraws
        coinbase = client.get_coinbase()
        password, unlock_seconds = client_credentials
        # https://github.com/ethereum/go-ethereum/wiki/Management-APIs#personal_unlockaccount
        client.make_request("personal_unlockAccount", [coinbase, password, unlock_seconds])

    client.mode = client_mode
    return client


@pytest.fixture(scope="module")
def coinbase(client):
    return client.get_coinbase()


@pytest.fixture(scope="module")
def hosted_wallet(client: Client, coinbase: str) -> HostedWallet:
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
def simple_test_contract(client, coinbase) -> ContractBase:
    """Create a contract where we can set a global variable for testing."""

    contract_meta = get_compiled_contract_cached("testcontract.sol", "TestContract")
    contract_class = Contract(contract_meta, "TestContract")
    address = deploy_contract_tx(client, geth_node, coinbase, contract_class)
    return contract_class(address, client)


@pytest.fixture(scope="module")
def token(client, coinbase) -> ContractBase:
    """Deploy a token contract in the blockchain."""
    contract_meta = get_compiled_contract_cached("token.sol", "Token")
    contract_class = Contract(contract_meta, "Token")

    # uint256 initialSupply,
    # string tokenName,
    # uint8 decimalUnits,
    # string tokenSymbol,
    # string nOfTheCode
    args = [10000, "Mootoken", 0, "MOO", "v1", coinbase]

    address = deploy_contract_tx(client, geth_node, coinbase, contract_class, constructor_args=args)
    return contract_class(address, client)



@pytest.fixture
def eth_network_id(dbsession):
    """Create service to talk with Ethereum network."""

    asset_network_name = "ethereum"

    with transaction.manager:
        network = get_eth_network(dbsession)
        return network.id



