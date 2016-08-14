"""Get the user phone number."""
import colander
import logging
import deform
from pyramid.renderers import render
from pyramid.view import view_config
from pyramid import httpexceptions

from pyramid_sms.validators import valid_international_phone_number
from websauna.system.core import messages
from websauna.system.form import rollingwindow
from websauna.system.form.schema import CSRFSchema
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation, ManualConfirmation, ManualConfirmationState
from websauna.wallet.views.confirm import AskConfirmation
from websauna.wallet.views.wallet import UserWallet


logger = logging.getLogger(__name__)


@colander.deferred
def throttle_new_phone_number_sign_ups(node, kw):
    request = kw["request"]

    def inner(node, value):
        # Check we don't have somebody brute forcing expires
        # TODO: Use per confirmation keys
        if rollingwindow.check(request.registry, "new_phone_number", window=60, limit=5):

            # Alert devops through Sentry
            logger.warn("Excessive new phone number sign ups")

            # Tell users slow down
            raise colander.Invalid(node, 'Too many phone number sign ups at the moment. Please try again later.')

    return inner


class NewPhoneNumber(CSRFSchema):
    phone_number = colander.SchemaNode(
        colander.String(),
        validators=[throttle_new_phone_number_sign_ups, valid_international_phone_number],
        title="Mobile phone number",
        desciption="Please give your mobile phone number in international format starting with + country code prefix. Example: +1 555 123 1234."

    )


def has_pending_phone_number_request(request: Request, user: User):
    return request.dbsession.query(UserNewPhoneNumberConfirmation).filter_by(user=user, state=ManualConfirmationState.pending).one_or_none()


@view_config(context=UserWallet, route_name="wallet", name="new-phone-number", renderer="wallet/new_phone_number.html")
def new_phone_number(wallet, request):

    user = wallet.user

    if has_pending_phone_number_request(request, user):
        return httpexceptions.HTTPFound(request.resource_url(wallet), "confirm-phone-number")

    schema = NewPhoneNumber().bind(request=request)

    b = deform.Button(name='process', title="Confirm", css_class="btn-block btn-lg")
    form = deform.Form(schema, buttons=(b,))

    # User submitted this form
    if request.method == "POST":
        if 'process' in request.POST:

            try:
                appstruct = form.validate(request.POST.items())

                # Save form data from appstruct
                phone_number = appstruct["phone_number"]
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
        return httpexceptions.HTTPFound(self.request.resource_url(wallet))

    def do_cancel(self):
        super(ConfirmPhoneNumber, self).do_cancel()
        wallet = self.context
        return httpexceptions.HTTPFound(self.request.resource_url(wallet))

    @view_config(context=UserWallet, route_name="wallet", name="confirm-phone-number", renderer="wallet/confirm_phone_number.html")
    def render(self):

        wallet = self.context  # type: UserWallet
        user = wallet.user
        request = self.request

        if not has_pending_phone_number_request(request, user):
            # We have confirmed the phone number, go to wallet root
            return httpexceptions.HTTPFound(self.request.resource_url(wallet))

        return self.act(locals())
