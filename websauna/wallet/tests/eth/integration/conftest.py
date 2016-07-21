import pytest

from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService


@pytest.fixture
def eth_service(client, eth_network_id, dbsession, registry):
    s = EthereumService(client, eth_network_id, dbsession, registry)
    register_eth_operations(registry)
    return s