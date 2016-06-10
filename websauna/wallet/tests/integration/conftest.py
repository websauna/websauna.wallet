"""Integration test fixtures."""
import pytest
import transaction

from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService


from websauna.wallet.models import AssetNetwork, CryptoAddress


@pytest.fixture
def eth_network_id(dbsession):
    """Create service to talk with Ethereum network."""

    asset_network_name = "ethereum"

    with transaction.manager:
        network = dbsession.query(AssetNetwork).filter_by(name=asset_network_name).one_or_none()
        if not network:
            network = AssetNetwork(name=asset_network_name)
            dbsession.add(network)
            dbsession.flush()  # Gives us network.id

        network_id = network.id

    return network_id


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
def eth_faux_address(dbsession, registry, eth_network_id):
    """Create a faux address that is not registered on node."""
    with transaction.manager:
        address = CryptoAddress(network_id=eth_network_id)
        address.address = "xxx"
    return address.address