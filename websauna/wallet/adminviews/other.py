from pyramid.view import view_config
from websauna.system.admin.utils import get_admin_url_for_sqlalchemy_object
from websauna.system.crud import listing
from websauna.system.http import Request
from websauna.system.core.viewconfig import view_overrides
from websauna.system.admin.views import Listing as DefaultListing
from websauna.system.admin.views import Show as DefaultShow
from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.utils import bin_to_eth_address
from websauna.wallet.models import UserOwnedAccount
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models import CryptoAddressAccount
from websauna.wallet.models import CryptoAddress
from websauna.wallet.utils import get_asset_formatter, format_asset_amount

from .. import admins


def get_user_for_account(view, column, user_owned_account: UserOwnedAccount):
    """Show user name."""
    return user_owned_account.user.friendly_name


def get_asset_for_account(view, column, user_owned_account: UserOwnedAccount):
    """Show the name of the asset user is owning."""
    return user_owned_account.account.asset.name


def get_amount_for_account(view, column, user_owned_account: UserOwnedAccount):
    """Format asset amount using a custom formatter, picked by asset type."""
    asset = user_owned_account.account.asset
    # Return a string like "{.2f}"
    formatter = get_asset_formatter(asset.asset_format)
    return formatter.format(user_owned_account.account.denormalized_balance)


def get_user_admin_link(request: Request, resource: admins.UserAccountAdmin.Resource):
    """Get link to a user admin show view from the user owned account."""
    user_account = resource.get_object()
    user = user_account.user
    admin = resource.get_admin()
    return get_admin_url_for_sqlalchemy_object(admin, user, "show")


class UserAccountListing(DefaultListing):
    """User listing modified to show the user hometown based on geoip of last login IP."""
    table = listing.Table(
        columns = [
            listing.Column("id", "Id",),
            listing.Column("user", "Owner", getter=get_user_for_account, navigate_url_getter=get_user_admin_link),
            listing.Column("asset", "Asset", getter=get_asset_for_account),
            listing.Column("amount", "Amount", getter=get_amount_for_account),
            listing.ControlsColumn()
        ]
    )

    @view_config(context=admins.UserAccountAdmin, name="listing", renderer="admin/account_listing.html", route_name="admin", permission='view')
    def listing(self):
        return super().listing()


@view_overrides(context=admins.UserAccountAdmin.Resource)
class UserAccountShow(DefaultShow):
    """User listing modified to show the user hometown based on geoip of last login IP."""

    includes = ["id",
                "user",
                "uuid",
                "account"
                "asset",
                ]

    def get_title(self):
        return "{}'s {} account".format(self.get_object().user.friendly_name, self.get_object().account.asset.name)


def find_user_for_account(view, column, resource):
    """Get link to a user admin show view from the user owned account."""
    account = resource
    request = view.request
    # TODO: Expensive. Should do in get_query()
    dbsession = request.dbsession
    ua = dbsession.query(UserCryptoAddress).join(CryptoAddress).join(CryptoAddressAccount).filter_by(account=account).first()
    if ua:
        return ua.user.friendly_name
    else:
        return "-"


@view_overrides(context=admins.CryptoAccounts)
class CryptoAccountListing(DefaultListing):
    """User listing modified to show the user hometown based on geoip of last login IP."""

    table = listing.Table(
        columns = [
            listing.Column("id", "Id",),
            listing.Column("user", "User", getter=find_user_for_account),
            listing.Column("asset", "Asset", getter=lambda v, c, account: account.asset.name),
            listing.Column("amount", "Amount", getter=lambda v, c, account: account.get_balance()),
            listing.ControlsColumn()
        ]
    )


def find_user_for_address(view, column, address):
    """Get link to a user admin show view from the user owned account."""
    request = view.request
    # TODO: Expensive. Should do in get_query()
    dbsession = request.dbsession
    ua = dbsession.query(UserCryptoAddress).filter_by(address=address).first()
    if ua:
        return ua.user.friendly_name
    else:
        return "-"


def find_eth_balance(view, column, address: CryptoAddress):
    """Get link to a user admin show view from the user owned account."""
    request = view.request
    # TODO: Expensive. Should do in get_query()
    dbsession = request.dbsession
    eth = get_ether_asset(dbsession)
    account = address.get_account(eth)
    if account:
        return format_asset_amount(account.account.get_balance(), account.account.asset.asset_class)
    else:
        return "-"



@view_overrides(context=admins.CryptoAddressAdmin)
class CryptoAddressListing(DefaultListing):
    """List all crypto addresses on the site."""

    table = listing.Table(
        columns = [
            listing.Column("user", "User", getter=find_user_for_address),
            listing.Column("network", "Network", getter=lambda v, c, address: address.network.name),
            listing.Column("address", "Address", getter=lambda v, c, address: bin_to_eth_address(address.address)),
            listing.Column("eth", "ETH balance", getter=find_eth_balance),
            listing.ControlsColumn()
        ]
    )



@view_overrides(context=admins.AssetNetworkAdmin)
class AssetNetworkListing(DefaultListing):
    """List all crypto addresses on the site."""

    table = listing.Table(
        columns = [
            listing.Column("id", "Id",),
            listing.Column("name", "Name", getter=lambda v, c, network: network.name),
            listing.ControlsColumn()
        ]
    )
