"""Assets administration with list, add and edit."""
import colander
import deform
import deform.widget

from websauna.system.crud import listing
from websauna.system.form.csrf import add_csrf
from websauna.system.form.fields import JSONValue, EnumValue, defer_widget_values
from websauna.system.form.resourceregistry import ResourceRegistry
from websauna.system.form.schema import CSRFSchema, enum_values, dictify, objectify
from websauna.system.form.sqlalchemy import UUIDForeignKeyValue
from websauna.system.form.widgets import JSONWidget
from websauna.utils.slug import uuid_to_slug
from websauna.viewconfig import view_overrides
from websauna.system.admin import views as adminbaseviews

from websauna.wallet import admins
from websauna.wallet.ethereum.utils import bin_to_eth_address, eth_address_to_bin
from websauna.wallet.models import AssetClass
from websauna.wallet.models.account import AssetState, Asset, AssetNetwork
from websauna.wallet.views.schemas import validate_ethereum_address


@view_overrides(context=admins.AssetAdmin)
class AssetNetworkListing(adminbaseviews.Listing):
    """List all crypto addresses on the site."""

    table = listing.Table(
        columns = [
            # listing.Column("id", "Id",),
            listing.Column("name", "Name", getter=lambda v, c, asset: asset.name),
            listing.Column("description", "Description", getter=lambda v, c, asset: asset.name),

            # Convert between binary storage and human readable hex presentation
            listing.Column("address", "Address", getter=lambda v, c, asset: asset.external_id and bin_to_eth_address(asset.external_id or "")),
            listing.ControlsColumn()
        ]
    )


def available_networks(node, kw):
    request = kw["request"]
    query = request.dbsession.query(AssetNetwork).all()
    return [(uuid_to_slug(network.id), network.name) for network in query]


class AssetSchema(colander.Schema):

    #: Human readable name
    name = colander.SchemaNode(colander.String())

    #:  The network this asset is in
    network = colander.SchemaNode(
        UUIDForeignKeyValue(model=AssetNetwork, match_column="id"),
        widget=defer_widget_values(deform.widget.SelectWidget, available_networks),
        )

    #: Symbol how this asset is presented in tickers
    symbol = colander.SchemaNode(colander.String())

    description = colander.SchemaNode(colander.String(), missing="")

    #: Markdown page telling about this asset
    long_description = colander.SchemaNode(colander.String(),
            description="Markdown formatted",
            missing="",
            widget=deform.widget.TextAreaWidget(rows=20, cols=80))

    #: Ethereum address
    external_id = colander.SchemaNode(colander.String(),
        title="Address",
        validator=validate_ethereum_address,
        missing=None,
        description="0x hex string format")

    #: Number of units avaialble
    supply = colander.SchemaNode(colander.Decimal(), missing=None)

    #: What kind of asset is this
    asset_class = colander.SchemaNode(EnumValue(AssetClass), widget=deform.widget.SelectWidget(values=enum_values(AssetClass)))

    #: Workflow state of this asset
    state = colander.SchemaNode(EnumValue(AssetState), widget=deform.widget.SelectWidget(values=enum_values(AssetState)))

    other_data = colander.SchemaNode(
        JSONValue(),
        widget=JSONWidget(),
        description="JSON bag of attributes of the object",
        missing=dict)

    def dictify(self, obj: Asset) -> dict:
        """Serialize SQLAlchemy model instance to nested dictionary appstruct presentation."""

        appstruct = dictify(self, obj, excludes=("long_description", "external_id"))

        # Convert between binary storage and human readable hex presentation
        appstruct["long_description"] = obj.other_data.pop("long_description", "")

        if obj.external_id:
            appstruct["external_id"] = bin_to_eth_address(obj.external_id)
        else:
            appstruct["external_id"] = ""

        return appstruct

    def objectify(self, appstruct: dict, obj: Asset):
        """Store the dictionary data from the form submission on the object."""

        objectify(self, appstruct, obj, excludes=("long_description", "external_id"))

        if not obj.other_data:
            # When creating the object JSON value may be None
            # instead of empty dict
            obj.other_data = {}

        # Special case of field stored inside JSON bag
        obj.other_data["long_description"] = appstruct["long_description"]

        # Convert between binary storage and human readable hex presentation
        if appstruct["external_id"]:
            obj.external_id = eth_address_to_bin(appstruct["external_id"])


class AssetFormMixin:
    """Provide serialization of SQLAlchemy Asset instance to Colander appstruct (dicts) and back."""

    def get_form(self):
        """Get Deform object we use on the admin page."""

        schema = getattr(self.request.registry, "asset_schema", None)
        if not schema:
            schema = AssetSchema()

        add_csrf(schema)

        schema = self.bind_schema(schema)

        return deform.form.Form(schema,
            buttons=self.get_buttons(),
            resource_registry=ResourceRegistry(self.request))

    def get_appstruct(self, form: deform.Form, obj: Asset) -> dict:
        """Serialize SQLAlchemy model instance to nested dictionary appstruct presentation."""
        appstruct = form.schema.dictify(obj)
        return appstruct

    def objectify_asset(self, form: deform.Form, appstruct: dict, obj: Asset):
        """Store the dictionary data from the form submission on the object."""
        form.schema.objectify(appstruct, obj)


@view_overrides(context=admins.AssetAdmin)
class AssetAdd(AssetFormMixin, adminbaseviews.Add):
    """Add new assets in admin."""

    def initialize_object(self, form: deform.Form, appstruct: dict, obj: Asset):
        # initialize_object and save_object are equal in our case
        self.objectify_asset(form, appstruct, obj)


@view_overrides(context=admins.AssetAdmin.Resource)
class AssetEdit(AssetFormMixin, adminbaseviews.Edit):
    """Edit existing asset in admin."""

    def save_changes(self, form: deform.Form, appstruct: dict, obj: Asset):
        """Store the dictionary data from the form submission on the object."""
        self.objectify_asset(form, appstruct, obj)

