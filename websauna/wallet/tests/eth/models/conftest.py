"""Integration test fixtures."""
import pytest
import transaction

from websauna.wallet.ethereum.asset import get_eth_network, get_ether_asset
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService


from websauna.wallet.models import AssetNetwork, CryptoAddress, Asset


@pytest.fixture
def eth_network_id(dbsession):
    """Create service to talk with Ethereum network."""

    asset_network_name = "ethereum"

    with transaction.manager:
        network = get_eth_network(dbsession)
        return network.id


@pytest.fixture
def eth_json_rpc(registry):
    """Create Ethereum RPC connection for integration tests."""
    return get_eth_json_rpc_client(registry)


@pytest.fixture
def eth_service(eth_json_rpc, eth_network_id, dbsession, registry):
    s = EthereumService(eth_json_rpc, eth_network_id, dbsession, registry)

    register_eth_operations(registry)

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