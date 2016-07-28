from typing import List

from pyramid import httpexceptions
from pyramid.decorator import reify
from pyramid.security import Allow
from pyramid.view import view_config

from websauna.system.core.route import simple_route
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.utils.slug import slug_to_uuid
from websauna.wallet.ethereum.asset import setup_user_account


class UserWallet:
    """Context object for wallet views for an user."""

    @reify
    def __acl__(self) -> List[tuple]:
        """Besides users themselves, we allow admins to view user wallets to troubleshoot issues."""
        owner_principal = "user:{}".format(self.request.user.id)
        return [(Allow, owner_principal, "view"),
                (Allow, "group:admin", "view")]

    def __init__(self, request, user):
        self.request = request
        self.user = user


class WalletRoot:
    """Sever user wallets from this URL."""

    def __init__(self, request):
        self.request = request

    def __getitem__(self, user_id):
        user = self.request.dbsession.query(User).filter_by(uuid=slug_to_uuid(user_id))
        return UserWallet(self.request, user)


@view_config(context=UserWallet, name="default", renderer="wallet/wallet.html")
def wallet(wallet: UserWallet, request: Request):
    """Wallet main page."""

    # Set up initial addresses if user doesn't have any yet
    setup_user_account(wallet.user)

    addresses = wallet.user.crypto_addresses
    return locals()