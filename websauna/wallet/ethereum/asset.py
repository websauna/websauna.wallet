"""Ethereum asset modelling."""
from sqlalchemy.orm import Session

from websauna.system.user.models import User
from websauna.wallet.models import AssetNetwork, Asset, AssetClass, UserCryptoAddress, CryptoAddressCreation
from websauna.wallet.models.blockchain import UserCryptoOperation, CryptoAddress


def get_eth_network(dbsession: Session, asset_network_name="ethereum") -> AssetNetwork:
    """Create Ethereum network instance.

    :param asset_network_name: What network we use. *ethereum* for main network, *testnet* for testnet.
    """

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

    # Ethereum supply is not stable
    # https://etherscan.io/stats/supply
    asset = Asset(name="Ether", symbol="ETH", asset_class=AssetClass.cryptocurrency, supply=0)
    network.assets.append(asset)
    dbsession.flush()
    return asset


def create_default_user_address(user: User, network: AssetNetwork) -> CryptoAddressCreation:
    """Initiate operation to create operation in a network."""
    dbsession = Session.object_session(user)
    ca = CryptoAddress(network=network)
    dbsession.add(ca)
    dbsession.flush()
    uca = UserCryptoAddress(address=ca, name="Default")
    user.owned_crypto_addresses.append(uca)
    dbsession.flush()
    op = CryptoAddressCreation(ca)
    op.crypto_address = uca.address
    user.owned_crypto_operations.append(UserCryptoOperation(crypto_operation=op))
    return op


def setup_user_account(user: User):
    """Setup hosted wallets on Ethereum and testnet networks."""
    dbsession = Session.object_session(user)
    for net in ("ethereum", "testnet"):
        ethereum = get_eth_network(dbsession, net)

        eth_addresses = user.owned_crypto_addresses.join(CryptoAddress).filter_by(network=ethereum)
        if eth_addresses.count() == 0:
            # Create default address
            create_default_user_address(user, ethereum)






