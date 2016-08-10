import colander
import deform

from websauna.system.form.sqlalchemy import convert_query_to_tuples
from websauna.system.form.sqlalchemy import UUIDForeignKeyValue
from websauna.utils.slug import uuid_to_slug

from websauna.wallet.models import AssetNetwork


@colander.deferred
def network_choice_widget(node: colander.SchemaNode, kw: dict):
    request = kw["request"]
    dbsession = request.dbsession
    query = dbsession.query(AssetNetwork)
    vocab = convert_query_to_tuples(
        query,
        first_column=lambda o: uuid_to_slug(o.id),
        second_column=lambda o: o.human_friendly_name)
    return deform.widget.SelectWidget(values=vocab)


def network_choice_node():
    """Create a colander.SchemaNode() with a drop down to choose one of AssetNetworks."""
    return colander.SchemaNode(

        # Convert selection widget UUIDs back to Customer objects
        UUIDForeignKeyValue(model=AssetNetwork, match_column="id"),

        title="Chain",

        # A SelectWidget with values lazily populated
        widget=network_choice_widget)
