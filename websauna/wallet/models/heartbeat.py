"""Maintain heartbeat status of each asset network."""
from uuid import UUID

import arrow
import datetime
import transaction
from sqlalchemy.orm import Session

from websauna.utils.time import now
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoNetworkStatus


def update_heart_beat(dbsession: Session, network_id: UUID, block_number: int):
    """Update heartbeat timestamp in the AssetNetwork, so we know this network is alive."""

    with transaction.manager:
        status = CryptoNetworkStatus.get_network_status(dbsession, network_id)
        status.data["heartbeat"] = {
            "timestamp": now().isoformat(),
            "block_number": block_number
        }


def is_network_alive(network: AssetNetwork, timeout=60):
    """Check if we have been succesfully communicating with the network recently."""

    session = Session.object_session(network)

    status = CryptoNetworkStatus.get_network_status(session, network.id)
    heartbeat_data = status.data.get("heartbeat")
    if not heartbeat_data:
        return False

    # Parse iso8601
    heartbeat = arrow.get(heartbeat_data["timestamp"]).datetime

    return heartbeat > now() - datetime.timedelta(seconds=timeout)
