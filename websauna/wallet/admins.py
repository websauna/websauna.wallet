from pyramid.security import Deny, Allow, Everyone
from websauna.system.admin.modeladmin import ModelAdmin, model_admin
from websauna.system.crud import Base64UUIDMapper
from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import CryptoAddressAccount

from .models import UserOwnedAccount
from .models import Asset
from .models import CryptoAddress
from .models import Account
from .models import     AssetNetwork


@model_admin(traverse_id="user-accounts")
class UserAccountAdmin(ModelAdmin):
    """Manage user owned accounts and their balances."""

    # Set permissions so that this information can be only shown,
    # never edited or deleted
    __acl__ = {
        (Deny, Everyone, 'add'),
        (Allow, 'group:admin', 'view'),
        (Deny, Everyone, 'edit'),
        #(Deny, Everyone, 'delete'),
    }

    title = "Accounting"

    singular_name = "user-account"
    plural_name = "user-accounts"
    model = UserOwnedAccount

    # UserOwnedAccount.id attribute is uuid type
    mapper = Base64UUIDMapper(mapping_attribute="id")

    class Resource(ModelAdmin.Resource):

        # Get something human readable about this object to the breadcrumbs bar
        def get_title(self):
            return self.get_object().user.friendly_name + ": " + self.get_object().account.asset.name


@model_admin(traverse_id="assets")
class AssetAdmin(ModelAdmin):
    """Manage user owned accounts and their balances."""
    #: Traverse title
    title = "Asset classes"

    singular_name = "asset"
    plural_name = "assets"
    model = Asset

    # UserOwnedAccount.id attribute is uuid type
    mapper = Base64UUIDMapper(mapping_attribute="id")

    class Resource(ModelAdmin.Resource):

        def get_title(self):
            return self.get_object().name


@model_admin(traverse_id="network")
class AssetNetworkAdmin(ModelAdmin):
    """Manage user owned accounts and their balances."""
    #: Traverse title
    title = "Networks"

    model = AssetNetwork

    # UserOwnedAccount.id attribute is uuid type
    mapper = Base64UUIDMapper(mapping_attribute="id")

    class Resource(ModelAdmin.Resource):

        def get_title(self):
            return self.get_object().name



@model_admin(traverse_id="wallets")
class CryptoAddressAdmin(ModelAdmin):
    """Manage user owned accounts and their balances."""
    #: Traverse title
    title = "Wallets"

    singular_name = "wallet"
    plural_name = "wallets"
    model = CryptoAddress

    # UserOwnedAccount.id attribute is uuid type
    mapper = Base64UUIDMapper(mapping_attribute="id")

    class Resource(ModelAdmin.Resource):

        def get_title(self):
            if not self.get_object().address:
                return "-"
            return eth_address_to_bin(self.get_object().address)


@model_admin(traverse_id="crypto-accounts")
class CryptoAccounts(ModelAdmin):
    """List all cypto address accounts and their balances.."""

    #: Traverse title
    title = "Crypto accounts"

    model = Account

    # UserOwnedAccount.id attribute is uuid type
    mapper = Base64UUIDMapper(mapping_attribute="id")

    class Resource(ModelAdmin.Resource):

        def get_title(self):
            if not self.get_object().asset.name:
                return "-"

    def get_query(self):
        """"""
        dbsession = self.get_dbsession()
        crypto_account_ids = dbsession.query(CryptoAddressAccount.account_id).all()
        return dbsession.query(Account).filter(Account.id.in_(crypto_account_ids))

