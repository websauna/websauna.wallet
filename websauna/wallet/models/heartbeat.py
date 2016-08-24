"""Maintain heartbeat status of each asset network."""
from uuid import UUID
import time
import datetime
import transaction

from sqlalchemy.orm import Session

from websauna.utils.time import now
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoNetworkStatus


def update_heart_beat(dbsession: Session, network_id: UUID, block_number: int, block_timestamp: float):
    """Update heartbeat timestamp in the AssetNetwork, so we know this network is alive."""

    with transaction.manager:
        status = CryptoNetworkStatus.get_network_status(dbsession, network_id)
        status.data["heartbeat"] = {
            "timestamp": time.time(),
            "block_number": block_number,
            "block_timestamp": block_timestamp,
        }


def is_network_alive(network: AssetNetwork, timeout=60, block_timeout=180, current_time=None):
    """Check if we have been succesfully communicating with the network recently."""

    session = Session.object_session(network)

    if not current_time:
        current_time = time.time()

    status = CryptoNetworkStatus.get_network_status(session, network.id)
    heartbeat_data = status.data.get("heartbeat")
    if not heartbeat_data:
        return False

    # Check if we have had a ping from network recently
    if heartbeat_data["timestamp"] < current_time - timeout:
        return False

    # Check if geth itself has been following blocks
    if block_timeout:
        if heartbeat_data["block_timestamp"] < current_time - block_timeout:
            return False

    return True


def dump_network_heartbeat(network: AssetNetwork):
    """Check if we have been succesfully communicating with the network recently."""

    session = Session.object_session(network)

    status = CryptoNetworkStatus.get_network_status(session, network.id)
    heartbeat_data = status.data.get("heartbeat")
    if not heartbeat_data:
        return {}

    return {
        "name": network.name,
        "geth_ping_seconds_ago": time.time() - heartbeat_data["timestamp"],
        "last_block_seconds_ago": time.time() - heartbeat_data["block_timestamp"],
    }
