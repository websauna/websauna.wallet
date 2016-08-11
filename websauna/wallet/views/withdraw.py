"""New address creation."""
import colander
import deform
from pyramid.httpexceptions import HTTPFound, HTTPInternalServerError
from pyramid.view import view_config
from websauna.system.core import messages
from websauna.system.form.schema import CSRFSchema
from websauna.wallet.ethereum.asset import get_required_confirmation_count
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models.blockchain import CryptoOperationType

from .wallet import UserAddressAsset
from .wallet import UserAddressFolder
from .wallet import UserWallet
from .schemas import network_choice_node
from .schemas import validate_ethereum_address
from .schemas import validate_withdraw_amount


class WithdrawSchema(CSRFSchema):

    address = colander.SchemaNode(
        colander.String(),
        title="To address",
        validators=[validate_ethereum_address])

    amount = colander.SchemaNode(
        colander.Decimal(),
        validators=[validate_withdraw_amount],
        description="Use dot (.) as a decimal separator")

    note = colander.SchemaNode(
        colander.String(),
        title="Note",
        description="For your own history")


@view_config(context=UserAddressAsset, route_name="wallet", name="withdraw", renderer="wallet/withdraw.html")
def withdraw(user_asset: UserAddressAsset, request):
    """List all addresses."""

    schema = WithdrawSchema().bind(request=request, user_asset=user_asset)

    # Create a styled button with some extra Bootstrap 3 CSS classes
    b = deform.Button(name='process', title="Withdraw", css_class="btn-block btn-lg")
    form = deform.Form(schema, buttons=(b,))

    title = "Withdraw"
    wallet = user_asset.wallet
    asset_resource = user_asset


    # User submitted this form
    if request.method == "POST":
        if 'process' in request.POST:

            try:
                appstruct = form.validate(request.POST.items())

                # Save form data from appstruct
                amount = appstruct["amount"]
                address = appstruct["address"]
                note = appstruct["note"]
                confirmations = get_required_confirmation_count(request.registry, user_asset.account.network, CryptoOperationType.withdraw)

                user_crypto_address = asset_resource.address.address
                user_crypto_address.withdraw(asset_resource.asset, amount, address, note, confirmations)

                # Thank user and take him/her to the next page
                messages.add(request, kind="info", msg="Please confirm withdraw", msg_id="msg-confirmation-needed")
                return HTTPFound(request.resource_url(wallet, "transactions"))

            except deform.ValidationFailure as e:
                # Render a form version where errors are visible next to the fields,
                # and the submitted values are posted back
                rendered_form = e.render()
        else:
            # We don't know which control caused form submission
            raise HTTPInternalServerError("Unknown form button pressed")
    else:
        # Render a form with initial values
        rendered_form = form.render()

    return locals()


