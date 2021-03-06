"""Ethereum asset modelling."""
from typing import Optional

import transaction
from sqlalchemy.orm import Session

from pyramid.registry import Registry
from websauna.system.user.models import User
from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.events import WalletCreated
from websauna.wallet.models import AssetNetwork, Asset, AssetClass, UserCryptoAddress, CryptoAddressCreation, UserCryptoOperation, CryptoAddress, CryptoAddressAccount
from websauna.wallet.models.blockchain import CryptoOperationType


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


def get_ether_asset(dbsession, network=None) -> Asset:
    """Create ETH cryptocurrency instance."""

    if not network:
        network = get_eth_network(dbsession)

    asset = dbsession.query(Asset).filter_by(network=network, symbol="ETH").one_or_none()
    if asset:
        return asset

    # Ethereum supply is not stable
    # https://etherscan.io/stats/supply
    asset = Asset(name="Ether", symbol="ETH", asset_class=AssetClass.ether, supply=0)
    network.assets.append(asset)
    dbsession.flush()
    return asset


def create_default_user_address(user: User, network: AssetNetwork, confirmations=1) -> CryptoAddressCreation:
    """Initiate operation to create operation in a network."""

    if network.name == "ethereum":
        name = "Default"
    else:
        name = "{} default".format(network.name.title())

    op = UserCryptoAddress.create_address(user, network, name, confirmations)
    return op


def setup_user_account(user: User, request=None, do_mainnet=False):
    """Setup hosted wallets on Ethereum and testnet networks."""

    if do_mainnet:
        # BBB with testing
        nets = ("ethereum", "testnet")
    else:
        nets = ("testnet",)

    dbsession = Session.object_session(user)
    for net in nets:
        ethereum = get_eth_network(dbsession, net)

        if request:
            # Read wanted number of confirmations from settings
            confirmations = get_required_confirmation_count(request.registry, ethereum, CryptoOperationType.create_address)
        else:
            # Use default
            confirmations = 1

        eth_addresses = user.owned_crypto_addresses.join(CryptoAddress).filter_by(network=ethereum)
        if eth_addresses.count() == 0:
            # Create default address
            create_default_user_address(user, ethereum, confirmations=confirmations)


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


def get_house_address(network: AssetNetwork) -> Optional[CryptoAddress]:
    """Gets a house crypto address which is used to fund user accounts, create initial tokens, etc."""
    dbsession = Session.object_session(network)
    address_id = network.other_data.get("house_address")
    if not address_id:
        return None
    return dbsession.query(CryptoAddress).get(address_id)


def create_house_address(network: AssetNetwork) -> CryptoAddressCreation:
    """Sets up house Ethereum account.

    Store CryptoAddress UUID under "house_address" key in network.other_data JSON bag.
    """

    assert not network.other_data.get("house_address")

    op = CryptoAddress.create_address(network)
    op.required_confirmation_count = 1
    addr_id = op.address.id
    assert addr_id
    network.other_data["house_address"] = str(addr_id)
    return op


def get_required_confirmation_count(registry: Registry, network: AssetNetwork, op_type: CryptoOperationType) -> int:
    """How many confirmations we require for some operations."""

    if network.name in ("testnet", "private testnet"):
        return 1

    # Production defaults
    op_map = {
        CryptoOperationType.withdraw: 3,
        CryptoOperationType.deposit: 6,
        CryptoOperationType.import_token: None,
        CryptoOperationType.create_token: 3,
        CryptoOperationType.create_address: 3
    }
    return op_map[op_type]
