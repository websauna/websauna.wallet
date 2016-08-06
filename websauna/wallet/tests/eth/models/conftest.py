"""Integration test fixtures."""
import pytest
import transaction

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.service import EthereumService


from websauna.wallet.models import AssetNetwork, CryptoAddress, Asset


@pytest.fixture
def eth_json_rpc(registry):
    """Create Ethereum RPC connection for integration tests."""
    return get_eth_json_rpc_client(registry)


@pytest.fixture
def eth_service(web3, eth_network_id, dbsession, registry):
    """Create Ethereum Service to run ops or mock ups."""
    s = EthereumService(web3, eth_network_id, dbsession, registry)
    return s


@pytest.fixture
def mock_eth_service(eth_network_id, dbsession, registry):
    """Non-functional Ethereum Service without a connection to geth."""

    from web3 import RPCProvider, Web3
    web3 = Web3(RPCProvider("127.0.0.1", 666))
    s = EthereumService(web3, eth_network_id, dbsession, registry)
    return s

@pytest.fixture
def testnet_service(web3, testnet_network_id, dbsession, registry):
    """Create Ethereum Service for testnet to run ops or mock ups."""
    s = EthereumService(web3, testnet_network_id, dbsession, registry)
    return s


@pytest.fixture
def eth_asset_id(dbsession):
    with transaction.manager:
        asset = get_ether_asset(dbsession)
        dbsession.flush()
        return asset.id


@pytest.fixture
def eth_faux_address(dbsession, registry, eth_network_id):
    """Create a faux address that is not registered on node."""
    with transaction.manager:
        address = CryptoAddress(network_id=eth_network_id)
        address.address = "xxx"
    return address.address