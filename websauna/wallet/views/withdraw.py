"""New address creation."""
import colander
import deform
from pyramid.httpexceptions import HTTPFound, HTTPInternalServerError
from pyramid.renderers import render
from pyramid.view import view_config
from websauna.system.core import messages
from websauna.system.form.schema import CSRFSchema
from websauna.wallet.ethereum.asset import get_required_confirmation_count
from websauna.wallet.ethereum.utils import eth_address_to_bin, bin_to_eth_address
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models.blockchain import CryptoOperationType, UserWithdrawConfirmation
from websauna.wallet.utils import format_asset_amount
from websauna.wallet.views.confirm import AskConfirmation
from websauna.wallet.views.network import get_network_resource

from .wallet import UserAddressAsset, UserOperation, get_user_crypto_operation_resource
from .schemas import validate_ethereum_address
from .schemas import validate_withdraw_amount


# 0x2f70d3d26829e412a602e83fe8eebf80255aeea5
# 0x0000000000000000000000000000000000000000

class WithdrawSchema(CSRFSchema):

    address = colander.SchemaNode(
        colander.String(),
        title="To address",
        validator=validate_ethereum_address,
        widget=deform.widget.TextInputWidget(size=6, maxlength=6, template="textinput_placeholder", placeholder="0x0000000000000000000000000000000000000000")
    )

    amount = colander.SchemaNode(
        colander.Decimal(),
        validator=validate_withdraw_amount,
        widget=deform.widget.TextInputWidget(size=6, maxlength=6, template="textinput_placeholder", placeholder="0.00")
        )

    note = colander.SchemaNode(
        colander.String(),
        title="Note",
        missing="",
        description="The note is recorded for your own transaction history.")


@view_config(context=UserAddressAsset, route_name="wallet", name="withdraw", renderer="wallet/withdraw.html")
def withdraw(user_asset: UserAddressAsset, request):
    """Ask user for the withdraw details."""

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

                # Create the withdraw
                user_withdraw = user_crypto_address.withdraw(asset_resource.asset, amount, address, note, confirmations)

                # Mark it as pending for confirmation
                UserWithdrawConfirmation.require_confirmation(user_withdraw)

                # Redirect user to the confirmation page
                user_crypto_operation_resource = get_user_crypto_operation_resource(request, user_withdraw)
                return HTTPFound(request.resource_url(user_crypto_operation_resource, "confirm-withdraw"))

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
    """Confirm user withdraw with SMS code."""

    def render_sms(self, template_context):

        op = self.context.op
        amount = format_asset_amount(op.amount, op.asset.asset_class)
        template_context.update({
            "amount": amount,
            "asset": op.asset.name,
            "address": bin_to_eth_address(op.external_address),
        })
        return render("wallet/sms/confirm_withdraw.txt", template_context, request=self.request)

    @property
    def manual_confirmation(self):
        return UserWithdrawConfirmation.get_pending_confirmation(self.context.uop)

    def do_success(self):
        super(ConfirmWithdraw, self).do_success()
        wallet = self.context.wallet
        messages.add(self.request, kind="success", msg="Withdraw on its way.", msg_id="msg-withdraw-confirmed")
        return HTTPFound(self.request.resource_url(wallet["transactions"]))

    def do_cancel(self):
        super(ConfirmWithdraw, self).do_cancel()
        wallet = self.context.wallet
        messages.add(self.request, kind="success", msg="Withdraw cancelled.", msg_id="msg-withdraw-cancelled")
        return HTTPFound(self.request.resource_url(wallet))

    def get_buttons(self):
        confirm = deform.Button(name='confirm', title="Verify")
        cancel = deform.Button(name='cancel', title="Cancel withdraw")
        return (confirm, cancel)

    @view_config(context=UserOperation, route_name="wallet", name="confirm-withdraw", renderer="wallet/confirm_withdraw.html")
    def render(self):
        wallet = self.context.wallet
        phone_number = wallet.user.user_data.get("phone_number")
        return self.act(extra_template_context=locals())
