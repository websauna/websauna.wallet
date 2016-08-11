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


def validate_ethereum_address(node, value, **kwargs):
    """Make sure the user gives a valid ethereum hex address."""

    if not value.startswith("0x"):
        raise colander.Invalid(node, "Please enter a hex address starting using 0x")

    if not len(value) == 42:
        raise colander.Invalid(node, "Ethereum address must be 42 characters, including 0x prefix")



def validate_withdraw_amount(node, value, **kwargs):
    """Make sure the user doesn't attempt to overdraw account."""

    user_account = kwargs["user_account"]

    if value <= 0:
        raise colander.Invalid(node, "Withdraw amount must be positive.")

    if value > user_account.balance:
        raise colander.Invalid(node, "The account holds balance of {}".format(user_account.balance))



