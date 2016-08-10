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

from .wallet import UserAddressFolder
from .wallet import UserWallet
from .schemas import network_choice_node


class CreateAddressSchema(CSRFSchema):

    name  = colander.SchemaNode(colander.String())

    network = network_choice_node()



@view_config(context=UserWallet, route_name="wallet", name="create-account", renderer="wallet/wallet_form.html")
def create_address(wallet: UserWallet, request):
    """List all addresses."""

    schema = CreateAddressSchema().bind(request=request)

    # Create a styled button with some extra Bootstrap 3 CSS classes
    b = deform.Button(name='process', title="Create", css_class="btn-block btn-lg")
    form = deform.Form(schema, buttons=(b,))

    # User submitted this form
    if request.method == "POST":
        if 'process' in request.POST:

            try:
                appstruct = form.validate(request.POST.items())

                # Save form data from appstruct
                network = appstruct["network"]
                name = appstruct["name"]
                confirmations = get_required_confirmation_count(request.registry, network, CryptoOperationType.create_address)
                UserCryptoAddress.create_address(wallet.user, network, name, confirmations)

                # Thank user and take him/her to the next page
                messages.add(request, kind="info", msg="New account is being created")
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

    title = "Create new account"

    return locals()


