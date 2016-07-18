import pytest
from eth_rpc_client import Client

from populus.contracts import deploy_contract
from populus.utils import get_contract_address_from_txn
from websauna.wallet.ethereum.ethjsonrpc import get_unlocked_json_rpc_client
from websauna.wallet.ethereum.wallet import get_wallet_contract_class

#: We enable populus plugin for this test file
#: http://doc.pytest.org/en/latest/plugins.html#requiring-loading-plugins-in-a-test-module-or-conftest-file
pytest_plugins = "populus.plugin",


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