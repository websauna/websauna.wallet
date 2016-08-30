"""Get the user phone number."""
import colander
import logging
import deform
from pyramid.renderers import render
from pyramid.view import view_config
from pyramid import httpexceptions

from pyramid_sms.utils import normalize_international_phone_number
from pyramid_sms.validators import valid_international_phone_number
from websauna.system.core import messages
from websauna.system.form import rollingwindow
from websauna.system.form.schema import CSRFSchema
from websauna.system.form.throttle import throttled_view
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation, ManualConfirmation, ManualConfirmationState
from websauna.wallet.views.confirm import AskConfirmation
from websauna.wallet.views.wallet import UserWallet


logger = logging.getLogger(__name__)



class NewPhoneNumber(CSRFSchema):

    phone_number = colander.SchemaNode(
        colander.String(),
        validator=valid_international_phone_number,
        title="Mobile phone number",
        default="+",
        description="Please give your mobile phone number in international format using with country code prefix with plus sign notation. Example: +1 555 123 1234.",
        widget=deform.widget.TextInputWidget(size=6, maxlength=6, type='tel', template="textinput_placeholder")

    )


def has_pending_phone_number_request(request: Request, user: User):
    return request.dbsession.query(UserNewPhoneNumberConfirmation).filter_by(user=user, state=ManualConfirmationState.pending).one_or_none()


@view_config(
    context=UserWallet,
    route_name="wallet",
    name="new-phone-number",
    renderer="wallet/new_phone_number.html",
    decorator=throttled_view(limit=999999))
def new_phone_number(wallet, request):

    user = wallet.user

    if has_pending_phone_number_request(request, user):
        return httpexceptions.HTTPFound(request.resource_url(wallet, "confirm-phone-number"))

    schema = NewPhoneNumber().bind(request=request)

    b = deform.Button(name='process', title="Send verification code", css_class="btn-block btn-lg")
    form = deform.Form(schema, buttons=(b,))

    # User submitted this form
    if request.method == "POST":
        if 'process' in request.POST:

            try:
                appstruct = form.validate(request.POST.items())

                # Save form data from appstruct
                phone_number = normalize_international_phone_number(appstruct["phone_number"])
                UserNewPhoneNumberConfirmation.require_confirmation(user, phone_number)

                return httpexceptions.HTTPFound(request.resource_url(wallet, "confirm-phone-number"))

            except deform.ValidationFailure as e:
                # Render a form version where errors are visible next to the fields,
                # and the submitted values are posted back
                rendered_form = e.render()
        else:
            # We don't know which control caused form submission
            raise httpexceptions.HTTPInternalServerError("Unknown form button pressed")
    else:
        # Render a form with initial values
        rendered_form = form.render()

    return locals()



class ConfirmPhoneNumber(AskConfirmation):
    """Get the confirmation code from the user phone number."""

    @property
    def manual_confirmation(self) -> UserNewPhoneNumberConfirmation:
        wallet = self.context
        return UserNewPhoneNumberConfirmation.get_pending_confirmation(wallet.user)

    def render_sms(self, template_context):
        return render("wallet/sms/confirm_phone_number.txt", template_context, request=self.request)
    
    def do_success(self):
        super(ConfirmPhoneNumber, self).do_success()
        wallet = self.context
        messages.add(self.request, kind="success", msg="Your mobile phone number has been confirmed.", msg_id="msg-phone-confirmed")

        wallet_welcome_page = self.request.registry.settings.get("websauna.wallet.welcome_page", "")

        return httpexceptions.HTTPFound(self.request.resource_url(wallet, wallet_welcome_page))

    def do_cancel(self):
        super(ConfirmPhoneNumber, self).do_cancel()
        wallet = self.context
        return httpexceptions.HTTPFound(self.request.resource_url(wallet))

    def get_buttons(self):
        confirm = deform.Button(name='confirm', title="Verify")
        cancel = deform.Button(name='cancel', title="Try again")
        return (confirm, cancel)

    @view_config(context=UserWallet, route_name="wallet", name="confirm-phone-number", renderer="wallet/confirm_phone_number.html")
    def render(self):

        wallet = self.context  # type: UserWallet
        user = wallet.user
        request = self.request
        phone_number = self.manual_confirmation.other_data["phone_number"]

        if not has_pending_phone_number_request(request, user):
            # We have confirmed the phone number, go to wallet root
            return httpexceptions.HTTPFound(self.request.resource_url(wallet))

        return self.act(locals())
