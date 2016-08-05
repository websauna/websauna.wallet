"""Maintain heartbeat status of each asset network."""
from uuid import UUID

import arrow
import transaction
from sqlalchemy.orm import Session

from websauna.utils.time import now
from websauna.wallet.models import AssetNetwork


def update_heart_beat(dbsession: Session, network_id: UUID):
    """Update heartbeat timestamp in the AssetNetwork, so we know this network is alive."""
    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(network_id)
        network.other_data["heartbeat"] = now().isoformat()


def is_network_alive(network: AssetNetwork, timeout=60):
    """Check if we have been succesfully communicating with the network recently."""

    heartbeat = network.other_data.get("heartbeat")

    # Parse iso8601
    heartbeat = arrow.get(heartbeat)
    deadline = arrow.utcnow().replace(seconds=-timeout)

    return heartbeat > deadline
