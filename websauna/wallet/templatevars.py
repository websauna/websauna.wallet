from pyramid.events import BeforeRender
from websauna.wallet.ethereum.asset import get_ether_asset, get_eth_network
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.utils import format_asset_amount


def get_default_balance(request):
    """Get ETH balance in Ethereum network."""

    user = request.user

    if not user:
        return None

    asset = get_ether_asset(request.dbsession)
    network = get_eth_network(request.dbsession)
    default_address = UserCryptoAddress.get_default(user, network)
    account = default_address.get_crypto_account(asset)

    if account:
        return format_asset_amount(account.account.get_balance(), asset.asset_class)
    else:
        return format_asset_amount(0, asset.asset_class)


def includeme(config):

    def on_before_render(event):
        # Augment Pyramid template renderers with these extra variables and deal with JS placement

        request = event["request"]
        event["default_balance"] = get_default_balance(request)

    config.add_subscriber(on_before_render, BeforeRender)