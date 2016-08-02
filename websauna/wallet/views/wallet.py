from typing import List

from pyramid import httpexceptions
from pyramid.decorator import reify
from pyramid.security import Allow
from pyramid.view import view_config

from websauna.system.core.root import Root
from websauna.system.core.route import simple_route
from websauna.system.core.traversal import Resource
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.utils.slug import slug_to_uuid, uuid_to_slug
from websauna.wallet.ethereum.asset import setup_user_account
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models.blockchain import UserCryptoOperation


class UserAddress(Resource):
    """URL endpoint for one managed address."""

    def __init__(self, request: Request, address: UserCryptoAddress):
        super(UserAddress, self).__init__(request)
        self.address = address


class UserAddressFolder(Resource):
    """Serve all address specific views for a user."""

    def __init__(self, request: Request, user: User):
        super(UserAddressFolder, self).__init__(request)
        self.user = user

    def get_addresses(self):
        addresses = self.user.owned_crypto_addresses
        for addr in addresses:
            ua = UserAddress(self.request, addr)
            yield Resource.make_lineage(self, ua, uuid_to_slug(addr.id))

    def __getitem__(self, item):
        uuid = slug_to_uuid(item)
        for addr in self.get_addresses():
            if addr.address.id == uuid:
                return addr
        raise KeyError()


class UserWallet(Resource):
    """Context object for wallet views for an user."""

    @reify
    def __acl__(self) -> List[tuple]:
        """Besides users themselves, we allow admins to view user wallets to troubleshoot issues."""
        owner_principal = "user:{}".format(self.request.user.id)
        return [(Allow, owner_principal, "view"),
                (Allow, "group:admin", "view")]

    def __init__(self, request: Request, user: User):
        super(UserWallet, self).__init__(request)
        self.user = user

        uaf = UserAddressFolder(request, user)
        self.address_folder = Resource.make_lineage(self, uaf, "accounts")

    def __getitem__(self, item):
        if item == "accounts":
            return self.address_folder
        raise KeyError()


class WalletFolder(Resource):
    """Sever UserWallets from this folder.

    Each user wallet is on its own url. Path is keyed by user UUID.
    """

    def __getitem__(self, user_id: str):
        user = self.request.dbsession.query(User).filter_by(uuid=slug_to_uuid(user_id)).one_or_none()
        if not user:
            raise KeyError()
        wallet = UserWallet(self.request, user)
        return Resource.make_lineage(self, wallet, user_id)


@view_config(context=WalletFolder, route_name="wallet", name="")
def wallet_root(wallet_root, request):
    """When wallet folder is accessed without path key, redirect to the users own wallet."""
    url = request.resource_url(wallet_root[uuid_to_slug(request.user.uuid)])
    return httpexceptions.HTTPFound(url)


@view_config(context=UserWallet, route_name="wallet", name="", renderer="wallet/wallet.html")
def wallet(wallet: UserWallet, request: Request):
    """Wallet main page."""

    # Set up initial addresses if user doesn't have any yet
    setup_user_account(wallet.user)

    active_operations = UserCryptoOperation.get_active_operations(wallet.user)

    return locals()


def route_factory(request):
    """Set up __parent__ and __name__ pointers required for traversal."""
    wallet_root = WalletFolder(request)
    root = Root.root_factory(request)
    return Resource.make_lineage(root, wallet_root, "wallet")
