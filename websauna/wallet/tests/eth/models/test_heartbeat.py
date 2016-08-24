"""Test Ethereum model operations."""

import transaction
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models.heartbeat import update_heart_beat, is_network_alive, dump_network_heartbeat

TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"

TEST_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"


def test_heartbeat(dbsession, eth_network_id, eth_service):
    """Create Ethereum account on Ethereum node."""

    update_heart_beat(dbsession, eth_network_id, 555, 555)

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        assert is_network_alive(network, current_time=556)
        assert not is_network_alive(network, current_time=999)


def test_dump_network_stats(dbsession, eth_network_id, eth_service):
    """Create Ethereum account on Ethereum node."""

    update_heart_beat(dbsession, eth_network_id, 555, 666)

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        dump_network_heartbeat(network)