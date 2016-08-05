"""Ethereum asset modelling."""
import transaction
from sqlalchemy.orm import Session

from websauna.system.user.models import User
from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import AssetNetwork, Asset, AssetClass, UserCryptoAddress, CryptoAddressCreation, UserCryptoOperation, CryptoAddress, CryptoAddressAccount


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


def get_toy_box(network: AssetNetwork) -> Asset:
    """Get the toybox asset."""

    if "initial_assets" not in network.other_data:
        return None

    toybox_id = network.other_data["initial_assets"].get("toybox")
    if not toybox_id:
        return

    dbsession = Session.object_session(network)

    return dbsession.query(Asset).get(toybox_id)

def get_house_holdings(asset: Asset) -> CryptoAddressAccount:
    """Get a asset holded by a house."""
    network = asset.network
    house_address = get_house_address(network)
    return house_address.get_account(asset)


def get_house_holdings_by_symbol(network: AssetNetwork, symbol: str) -> CryptoAddressAccount:
    """Get a asset holded by a house."""
    asset = network.get_asset_by_symbol(symbol)
    return get_house_holdings(network, asset)


def get_house_address(network: AssetNetwork) -> CryptoAddress:
    """Gets a house crypto address which is used to fund user accounts, create initial tokens, etc."""
    dbsession = Session.object_session(network)
    address_id = network.other_data["house_address"]
    return dbsession.query(CryptoAddress).get(address_id)


def create_house_address(network: AssetNetwork) -> CryptoAddressCreation:
    """Sets up house Ethereum account.

    Store CryptoAddress UUID under "house_address" key in network.other_data JSON bag.
    """

    assert not network.other_data.get("house_address")

    op = CryptoAddress.create_address(network)
    addr_id = op.address.id
    assert addr_id
    network.other_data["house_address"] = str(addr_id)
    return op



