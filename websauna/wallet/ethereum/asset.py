"""Ethereum asset modelling."""
from sqlalchemy.orm import Session
from websauna.wallet.models import AssetNetwork, Asset


def get_eth_network(dbsession: Session, asset_network_name="ethereum") -> AssetNetwork:
    """Create Ethereum network instance."""

    network = dbsession.query(AssetNetwork).filter_by(name=asset_network_name).one_or_none()
    if not network:
        network = AssetNetwork(name=asset_network_name)
        dbsession.add(network)
        dbsession.flush()  # Gives us network.id
    return network


def get_ether_asset(dbsession) -> Asset:
    """Create ETH cryptocurrency instance."""
    network = get_eth_network(dbsession)

    asset = dbsession.query(Asset).filter_by(network=network, symbol="ETH").one_or_none()
    if asset:
        return asset

    asset = Asset(name="Ether", symbol="ETH")
    network.assets.append(asset)
    dbsession.flush()
    return asset
