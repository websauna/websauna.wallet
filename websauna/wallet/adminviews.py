from pyramid.view import view_config
from pyramid_layout.panel import panel_config
from websauna.system.admin.utils import get_admin_url_for_sqlalchemy_object
from websauna.system.crud import listing
from websauna.system.http import Request
from websauna.viewconfig import view_overrides
from websauna.system.admin.views import Listing as DefaultListing
from websauna.system.admin.views import Show as DefaultShow
from websauna.wallet.models import UserOwnedAccount
from websauna.wallet.utils import get_asset_formatter

from . import admins


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







