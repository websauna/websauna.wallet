from pyramid.security import Deny, Allow, Everyone
from websauna.system.admin.modeladmin import ModelAdmin, model_admin
from websauna.system.crud import Base64UUIDMapper

from .models import UserOwnedAccount
from .models import Asset


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


@model_admin(traverse_id="user-accounts")
class AssetAdmin(ModelAdmin):
    """Manage user owned accounts and their balances."""
    #: Traverse title
    title = "Asset types"

    singular_name = "asset"
    plural_name = "assets"
    model = Asset

    # UserOwnedAccount.id attribute is uuid type
    mapper = Base64UUIDMapper(mapping_attribute="id")

    class Resource(ModelAdmin.Resource):

        def get_title(self):
            import pdb ; pdb.set_trace()
            return self.get_object().friendly_name