"""Test Ethereum account operations."""
import transaction

from websauna.wallet.models import AssetNetwork


def test_create_ath_account(dbsession, eth_network_id, eth_service):
    """Create Ethereum account on Ethereum node."""


    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
