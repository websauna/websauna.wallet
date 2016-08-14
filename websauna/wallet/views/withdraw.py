"""New address creation."""
import colander
import deform
from pyramid.httpexceptions import HTTPFound, HTTPInternalServerError
from pyramid.view import view_config
from websauna.system.core import messages
from websauna.system.form.schema import CSRFSchema
from websauna.wallet.ethereum.asset import get_required_confirmation_count
from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models.blockchain import CryptoOperationType
from websauna.wallet.utils import format_asset_amount
from websauna.wallet.views.confirm import AskConfirmation
from websauna.wallet.views.network import get_network_resource

from .wallet import UserAddressAsset, UserOperation
from .schemas import validate_ethereum_address
from .schemas import validate_withdraw_amount


class WithdrawSchema(CSRFSchema):

    address = colander.SchemaNode(
        colander.String(),
        title="To address",
        validator=validate_ethereum_address,
        description="Ethereum address as 0x prefixed hex string format")

    amount = colander.SchemaNode(
        colander.Decimal(),
        validator=validate_withdraw_amount,
        description="Use dot (.) as a decimal separator")

    note = colander.SchemaNode(
        colander.String(),
        title="Note",
        description="For your own history")


@view_config(context=UserAddressAsset, route_name="wallet", name="withdraw", renderer="wallet/withdraw.html")
def withdraw(user_asset: UserAddressAsset, request):
    """List all addresses."""


    title = "Withdraw"
    wallet = user_asset.wallet
    asset_resource = user_asset
    network_resource = get_network_resource(request, asset_resource.asset.network)
    balance = format_asset_amount(user_asset.balance, user_asset.asset.asset_class)
    address_resource = asset_resource.address
    account = user_asset.account

    schema = WithdrawSchema().bind(request=request, account=account)
    b = deform.Button(name='process', title="Withdraw", css_class="btn-block btn-lg")
    form = deform.Form(schema, buttons=(b,))

    # User submitted this form
    if request.method == "POST":
        if 'process' in request.POST:

            try:
                appstruct = form.validate(request.POST.items())

                # Save form data from appstruct
                amount = appstruct["amount"]
                address = eth_address_to_bin(appstruct["address"])
                note = appstruct["note"]
                confirmations = get_required_confirmation_count(request.registry, user_asset.account.asset.network, CryptoOperationType.withdraw)

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



class ConfirmWithdraw(AskConfirmation):

    @property
    def manual_confirmation(self):
        return self.context.manual_confirmation

    @view_config(context=UserOperation, route_name="wallet", name="confirm-withdraw", renderer="wallet/confirm_withdraw.html")
    def render(self):
        return self.act()
