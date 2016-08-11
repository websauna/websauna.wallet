from typing import List, Iterable

from decimal import Decimal
from pyramid import httpexceptions
from pyramid.decorator import reify
from pyramid.security import Allow
from pyramid.view import view_config
from websauna.system.core.breadcrumbs import get_breadcrumbs

from websauna.system.core.root import Root
from websauna.system.core.traversal import Resource
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.utils.slug import slug_to_uuid, uuid_to_slug
from websauna.wallet.ethereum.asset import setup_user_account
from websauna.wallet.ethereum.utils import bin_to_eth_address, bin_to_txid
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models import UserCryptoOperation
from websauna.wallet.models import CryptoOperationState
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import Account
from websauna.wallet.models import Asset
from websauna.wallet.models import CryptoAddressAccount
from websauna.wallet.models.blockchain import CryptoOperationType
from websauna.wallet.utils import format_asset_amount
from websauna.wallet.views.network import get_asset_resource
from websauna.wallet.views.network import get_network_resource


OP_STATES = {
    CryptoOperationState.waiting: "Scheduled for operation",
    CryptoOperationState.pending: "Waiting for broadcasting to network",
    CryptoOperationState.broadcasted: "Waiting for more confirmations",
    CryptoOperationState.success: "Success",
    CryptoOperationState.failed: "Failure",
}


class UserAddressAsset(Resource):
    """Asset in user wallet.

    * Withdraw

    * Transaction history

    """

    def __init__(self, request: Request, crypto_account: CryptoAddressAccount):
        super(UserAddressAsset, self).__init__(request)
        self.crypto_account = crypto_account

    def get_title(self):
        return "{} ({})".format(self.account.asset.name, self.account.asset.symbol)

    @property
    def account(self):
        return self.crypto_account.account

    @property
    def user(self) -> User:
        return self.wallet.user

    @property
    def wallet(self) -> "UserWallet":
        return self.__parent__.__parent__.__parent__

    @property
    def address(self) -> "UserAddress":
        return self.__parent__

    @property
    def balance(self) -> Decimal:
        return self.account.get_balance()

    @property
    def asset(self) -> Asset:
        return self.crypto_account.account.asset

    def get_latest_ops(self, limit=5):
        dbsession = self.request.dbsession
        for uco in dbsession.query(UserCryptoOperation).filter_by(user=self.user).join(CryptoOperation).filter_by(crypto_account=self.crypto_account).order_by(CryptoOperation.created_at.desc())[0:limit]:
            yield get_user_crypto_operation_resource(self.request, uco)


class UserAddress(Resource):
    """URL endpoint for one managed address."""

    def __init__(self, request: Request, address: UserCryptoAddress):
        super(UserAddress, self).__init__(request)
        self.address = address

    def __str__(self):
        return str(self.address.address)

    def get_user(self):
        return self.__parent__.user

    def get_title(self):
        return self.address.name

    def get_user_address_asset(self, crypto_account: CryptoAddressAccount):
        uaa = UserAddressAsset(self.request, crypto_account)
        return Resource.make_lineage(self, uaa, uuid_to_slug(crypto_account.id))

    def get_latest_ops(self, limit=5):
        dbsession = self.request.dbsession
        for uco in dbsession.query(UserCryptoOperation).filter_by(user=self.get_user()).join(CryptoOperation).order_by(CryptoOperation.created_at.desc())[0:limit]:
            yield get_user_crypto_operation_resource(self.request, uco)

    def get_assets(self) -> Iterable[UserAddressAsset]:
        """Get all assets under this address."""
        dbsession = self.request.dbsession
        for crypto_account in dbsession.query(CryptoAddressAccount).filter_by(address=self.address.address).join(Account).order_by(Account.created_at.desc()):
            yield self.get_user_address_asset(crypto_account)

    def __getitem__(self, item):
        dbsession = self.request.dbsession
        crypto_account = dbsession.query(CryptoAddressAccount).filter_by(address=self.address.address).filter_by(id=slug_to_uuid(item)).one_or_none()
        if crypto_account:
            return self.get_user_address_asset(crypto_account)
        raise KeyError()



class UserOperation(Resource):

    def __init__(self, request: Request, uop: UserCryptoOperation):
        super(UserOperation, self).__init__(request)
        self.uop = uop

    def get_title(self):
        op = self.uop.crypto_operation
        if op.has_txid():
            if op.txid:
                tx_name = bin_to_txid(op.txid)
            else:
                tx_name = "<transaction hash pending>"
        else:
            if op.external_address:
                tx_name = "bad"
            else:
                tx_name = "foo"

        return tx_name

    def __str__(self):
        return str(self.uop.op)


class UserAddressFolder(Resource):
    """Serve all address specific views for a user."""

    def __init__(self, request: Request, user: User):
        super(UserAddressFolder, self).__init__(request)
        self.user = user

    @property
    def wallet(self) -> "UserWallet":
        return self.__parent__

    def get_title(self):
        return "Accounts"

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


class UserOperationFolder(Resource):
    """Serve all operation specific views for a user."""

    def __init__(self, request: Request, wallet: "UserWallet"):
        super(UserOperationFolder, self).__init__(request)
        self.wallet = wallet

    def get_title(self):
        return "Transactions"

    def get_operations(self, state: Iterable):

        ops = self.wallet.user.owned_crypto_operations.join(CryptoOperation).filter(CryptoOperation.state.in_(state)).order_by(
            CryptoOperation.created_at.desc())
        for op in ops:
            uo = UserOperation(self.request, op)
            yield Resource.make_lineage(self, uo, uuid_to_slug(op.id))

    def __getitem__(self, item):
        uuid = slug_to_uuid(item)
        uop = self.request.dbsession.query(UserCryptoOperation).get(uuid)

        if not uop:
            raise KeyError()

        if uop.user != self.wallet.user:
            raise httpexceptions.HTTPForbidden()

        return Resource.make_lineage(self, UserOperation(self.request, uop), uuid_to_slug(uop.id))


class UserWallet(Resource):
    """Context object for wallet views for an user."""

    @reify
    def __acl__(self) -> List[tuple]:
        """Besides users themselves, we allow admins to view user wallets to troubleshoot issues."""
        owner_principal = "user:{}".format(self.request.user.id)
        return [(Allow, owner_principal, "view"),
                (Allow, "group:admin", "view")]

    def get_title(self):
        return "{}'s wallet".format(self.user.friendly_name)

    def __init__(self, request: Request, user: User):
        super(UserWallet, self).__init__(request)
        self.user = user

        uaf = UserAddressFolder(request, user)
        uof = UserOperationFolder(request, self)
        self.address_folder = Resource.make_lineage(self, uaf, "accounts")
        self.op_folder = Resource.make_lineage(self, uof, "transactions")

    def __getitem__(self, item):
        if item == "accounts":
            return self.address_folder

        if item == "transactions":
            return self.op_folder

        raise KeyError()

    def get_address_resource(self, address: UserCryptoAddress) -> UserAddress:
        assert address.user == self.user
        return self["accounts"][uuid_to_slug(address.id)]

    def get_uop_resource(self, uop: UserCryptoOperation) -> UserOperation:
        assert uop.user == self.user
        return self["transactions"][uuid_to_slug(uop.id)]

    def list_all_assets(self):
        """Get all assets under all addresses."""

        for user_address in self["accounts"].get_addresses():
            for asset in user_address.get_assets():
                yield asset


class WalletFolder(Resource):
    """Sever UserWallets from this folder.

    Each user wallet is on its own url. Path is keyed by user UUID.
    """

    def get_title(self):
        return "Wallets"

    def get_user_wallet(self, user):
        wallet = UserWallet(self.request, user)
        return Resource.make_lineage(self, wallet, uuid_to_slug(user.uuid))

    def __getitem__(self, user_id: str):
        user = self.request.dbsession.query(User).filter_by(uuid=slug_to_uuid(user_id)).one_or_none()
        if not user:
            raise KeyError()
        return self.get_user_wallet(user)


@view_config(context=WalletFolder, route_name="wallet", name="")
def wallet_root(wallet_root, request):
    """When wallet folder is accessed without path key, redirect to the users own wallet."""
    url = request.resource_url(wallet_root[uuid_to_slug(request.user.uuid)])
    return httpexceptions.HTTPFound(url)


def describe_address(request, ua: UserAddress) -> dict:
    """Fetch address details and link data for rendering."""
    detail = {}
    detail["user_address"] = ua
    detail["address"] = ua.address.address
    detail["network_resource"] = get_network_resource(request, ua.address.address.network)
    detail["name"] = ua.address.name
    detail["op"] = ua.address.address.get_creation_op()
    return detail


def describe_user_address_asset(request, uaa: UserAddressAsset) -> dict:
    """Fetch user asset holding details."""
    entry = {}
    account = uaa.crypto_account.account
    entry["name"] = uaa.get_title()
    entry["account"] = uaa.crypto_account.account
    entry["asset_resource"] = uaa
    entry["type"] = account.asset.asset_class.value
    entry["address_resource"] = uaa.address
    entry["balance"] = format_asset_amount(account.get_balance(), account.asset.asset_class)
    entry["network_resource"] = get_network_resource(request, account.asset.network)
    entry["can_withdraw"] = account.get_balance() > 0
    return entry


def describe_operation(request, uop: UserOperation) -> dict:
    """Fetch operation details and link data for rendering."""
    assert isinstance(uop, UserOperation)
    detail = {}
    op = uop.uop.crypto_operation
    detail["op"] = op
    if op.holding_account and op.holding_account.asset:
        detail["asset_resource"] = get_asset_resource(request, op.holding_account.asset)

    confirmations = op.calculate_confirmations()

    if confirmations is not None:
        if confirmations > 30:
            confirmations = "30+"
        detail["confirmations"] = confirmations

    if op.external_address:
        detail["address"] = bin_to_eth_address(op.external_address)
        if op.operation_type in (CryptoOperationType.deposit, CryptoOperationType.import_token):
            detail["address_label"] = "From {}".format(detail["address"])
        elif op.operation_type in (CryptoOperationType.withdraw,):
            detail["address_label"] = "To {}".format(detail["address"])
        else:
            detail["address_label"] = detail["address"]

    if op.txid:
        detail["txid"] = bin_to_txid(op.txid)

    amount = op.amount

    if amount:
        detail["amount"] = format_asset_amount(amount, op.asset.asset_class)

    detail["uuid"] = str(uop.uop.id)
    detail["resource"] = uop
    detail["tx_name"] = uop.get_title()
    detail["state"] = OP_STATES[op.state]
    detail["address_resource"] = get_user_address_resource(request, op.address)
    detail["network_resource"] = get_network_resource(request, op.network)

    return detail


@view_config(context=UserOperationFolder, route_name="wallet", name="", renderer="wallet/ops.html")
def operations_root(op_root: UserOperationFolder, request):
    """When wallet folder is accessed without path key, redirect to the users own wallet."""
    wallet = op_root.wallet

    pending_operations= op_root.get_operations(state=[CryptoOperationState.waiting, CryptoOperationState.broadcasted, CryptoOperationState.pending])
    pending_operations = [describe_operation(request, uop) for uop in pending_operations]

    finished_operations = op_root.get_operations(state=[CryptoOperationState.success, CryptoOperationState.failed])
    finished_operations = [describe_operation(request, uop) for uop in finished_operations]

    breadcrumbs = get_breadcrumbs(op_root, request)

    return locals()


@view_config(context=UserOperation, route_name="wallet", name="", renderer="wallet/op.html")
def operation(uop: UserOperation, request):
    """Single operation in a wallet."""
    detail = describe_operation(request, uop)
    op = detail["op"]
    wallet = uop.__parent__.__parent__
    breadcrumbs = get_breadcrumbs(uop, request)
    return locals()


@view_config(context=UserAddress, route_name="wallet", name="", renderer="wallet/address.html")
def address(ua: UserAddress, request):
    """Show single address."""
    wallet = ua.__parent__.__parent__
    latest_ops = [describe_operation(request, op) for op in ua.get_latest_ops()]
    assets = [describe_user_address_asset(request, op) for op in ua.get_assets()]
    detail = describe_address(request, ua)
    breadcrumbs = get_breadcrumbs(ua, request)
    return locals()


@view_config(context=UserAddressFolder, route_name="wallet", name="", renderer="wallet/addresses.html")
def addresses(uaf: UserAddressFolder, request):
    """List all addresses."""
    wallet = uaf.__parent__
    details = [describe_address(request, address) for address in uaf.get_addresses()]
    breadcrumbs = get_breadcrumbs(uaf, request)
    return locals()


@view_config(context=UserAddressAsset, route_name="wallet", name="", renderer="wallet/asset.html")
def asset(uaa: UserAddressAsset, request):
    """Show single address."""
    wallet = uaa.wallet
    assert isinstance(wallet, UserWallet)
    detail = describe_user_address_asset(request, uaa)
    latest_ops = [describe_operation(request, uop) for uop in uaa.get_latest_ops()]
    breadcrumbs = get_breadcrumbs(uaa, request)
    return locals()


@view_config(context=UserWallet, route_name="wallet", name="", renderer="wallet/wallet.html")
def wallet(wallet: UserWallet, request: Request):
    """Wallet Overview page."""

    # Whose wallet we are dealing with
    user = wallet.user

    # Set up initial addresses if user doesn't have any yet
    setup_user_account(user)

    asset_details = [describe_user_address_asset(request, asset) for asset in wallet.list_all_assets()]
    breadcrumbs = get_breadcrumbs(wallet, request)

    return locals()


def route_factory(request):
    """Set up __parent__ and __name__ pointers required for traversal."""
    wallet_root = WalletFolder(request)
    root = Root.root_factory(request)
    return Resource.make_lineage(root, wallet_root, "wallet")


def get_user_crypto_operation_resource(request, uop: UserCryptoOperation) -> UserOperation:
    assert isinstance(uop, UserCryptoOperation)
    wallet_root = WalletFolder(request)
    wallet = wallet_root[uuid_to_slug(uop.user.uuid)]
    return wallet.get_uop_resource(uop)


def get_user_address_resource(request, address: CryptoAddress):
    uca = UserCryptoAddress.get_by_address(address)
    if not uca:
        return None
    wallet_root = route_factory(request)
    wallet = wallet_root.get_user_wallet(uca.user)
    return wallet.get_address_resource(uca)



