"""Get the initial user phone number."""
import colander
from websauna.wallet.tests.eth.models.sms import AskConfirmation
import logging
import deform
from pyramid.view import view_config
from pyramid import httpexceptions

from websauna.system.form import rollingwindow
from websauna.system.http import Request
from websauna.system.user.models import User
from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation, ManualConfirmation
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


class NewPhoneNumber(colander.Schema):
    phone_number = colander.SchemaNode(
        colander.String(),
        title="Mobile phone number",
        desciption="Please give your mobile phone number in international format."

    )


def has_pending_phone_number_request(request: Request, user: User):
    return request.dbsession.query(UserNewPhoneNumberConfirmation).filter_by(user=user, state=ManualConfirmation.pending).one_or_none()


@view_config(context=UserWallet, route_name="wallet", name="give-new-phone-number")
def new_phone_number(wallet, request):

    user = wallet.user

    if has_pending_phone_number_request(user):
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
                user.user_data["pending_phone_number"] = phone_number



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

    @property
    def manual_confirmation(self):
        return self.context.manual_confirmation

    @view_config(context=UserWallet, route_name="wallet", name="confirm-phone-number", renderer="wallet/new_phone_number.html")
    def render(self):
        return self.act()
