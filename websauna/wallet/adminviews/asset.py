import colander
import deform
import deform.widget
from enum import enum
from shareregistry.utils import bin_to_eth_address, eth_address_to_bin

from websauna.system.crud import listing
from websauna.system.form.schema import CSRFSchema, enum_values, validate_json
from websauna.system.form.widgets import JSONWidget
from websauna.viewconfig import view_overrides
from websauna.system.admin import views as adminbaseviews


from websauna.wallet import admins
from websauna.wallet.models import AssetClass
from websauna.wallet.models.account import AssetState, Asset
from websauna.wallet.views.schemas import validate_ethereum_address


@view_overrides(context=admins.AssetAdmin)
class AssetNetworkListing(adminbaseviews.Listing):
    """List all crypto addresses on the site."""

    table = listing.Table(
        columns = [
            listing.Column("id", "Id",),
            listing.Column("name", "Name", getter=lambda v, c, asset: asset.name),
            listing.Column("description", "Description", getter=lambda v, c, asset: asset.name),
            listing.Column("address", "Address", getter=lambda v, c, asset: asset.external_id and bin_to_eth_address(asset.external_id or "")),
            listing.ControlsColumn()
        ]
    )


class AssetSchema(CSRFSchema):

    name = colander.SchemaNode(colander.String())
    symbol = colander.SchemaNode(colander.String())
    description = colander.SchemaNode(colander.String())
    long_description = colander.SchemaNode(colander.String(),
            description="Markdown formatted",
            widget=deform.widget.TextAreaWidget(rows=80, cols=20))
    external_id = colander.SchemaNode(colander.String(), title="Address", validator=validate_ethereum_address, missing=None)
    supply = colander.SchemaNode(colander.Decimal())
    asset_class = colander.SchemaNode(colander.String(), widget=deform.widget.SelectWidget(values=enum_values(AssetClass)))
    state = colander.SchemaNode(colander.String(), widget=deform.widget.SelectWidget(values=enum_values(AssetState)))
    other_data = colander.SchemaNode(colander.String(), validator=validate_json, widget=JSONWidget())


@view_overrides(context=admins.AssetAdmin)
class AssetEdit(adminbaseviews.Edit):
    """Edit asset in admin."""

    def get_form(self):
        schema = AssetSchema()
        schema = self.bind_schema(schema)
        return deform.form.Form(schema, buttons=self.get_buttons())

    def get_appstruct(self, form: deform.Form, obj: Asset) -> dict:
        appstruct = super(AssetEdit, self).get_appstruct(form, obj)
        appstruct["long_description"] = obj.other_data["long_description"]
        appstruct["external_id"] = bin_to_eth_address(obj.external_id)

    def save_changes(self, form: deform.Form, appstruct: dict, obj: Asset):
        """Store the data from the form on the object."""
        form.schema.objectify(appstruct, obj)
        obj.other_data["long_description"] = appstruct["long_description"]
        obj.external_id = eth_address_to_bin(obj.external_id)

