import logging
import colander
import deform
from pyramid.request import Request
from pyramid import httpexceptions
import colander as c
from pyramid_sms.outgoing import send_sms, send_templated_sms
from websauna.system.core import messages
from websauna.system.form import rollingwindow
from websauna.system.form.schema import CSRFSchema
from websauna.utils.time import now
from websauna.wallet.models import ManualConfirmation


logger = logging.getLogger(__name__)


@c.deferred
def throttle_confirmation_attempts(node, kw):
    """Protect against brute forcing."""
    request = kw["request"]

    def inner(node, value):
        # Check we don't have somebody brute forcing expires
        # TODO: Use per confirmation keys
        if rollingwindow.check(request.registry, "confirm_action", window=60, limit=5):

            # Alert devops through Sentry
            logger.warn("Excessive confirmation traffic")

            # Tell users slow down
            raise colander.Invalid(node, 'Too many confirmation attempts. Please try again later.')

    return inner


@c.deferred
def validate_sms_code(node, kw):
    """Protect against brute forcing."""
    request = kw["request"]
    manual_confirmation = kw["manual_confirmatoin"]

    def validate(node, value):
        if value != manual_confirmation.other_data["sms_code"]:
            raise colander.Invalid("Confirmation code was not correct.")


class SMSConfirmationSchema(CSRFSchema):

    code = colander.SchemaNode(colander.String(),
        title="Verification code",
        validators=[throttle_confirmation_attempts, validate_sms_code],
        widget=deform.widget.TextInputWidget(size=6, maxlength=6, type='tel', template="textinput_placeholder", placeholder="000000")
        )


class AskConfirmation:
    """Generic confirmation view for SMS codes."""

    def __init__(self, context, request: Request):
        self.context = context
        self.request = request

    @property
    def manual_confirmation(self) -> ManualConfirmation:
        raise NotImplementedError()

    def do_success(self):
        """Override in subclass to take action when confirmation success."""
        self.success()
        pass

    def do_cancel(self):
        """Override in subclass to take action when user cancels."""
        self.cancel()
        pass

    def capture_data(self):
        return {
            "ip": str(self.request.client_addr),
            "user_agent": self.request.user_agent
        }

    def cancel(self):
        self.manual_confirmation.cancel(self.capture_data())

    def success(self):
        self.manual_confirmation.resolve(self.capture_data())

    def get_target_phone_number(self):
        """Get the user's phone number."""
        return self.manual_confirmation.other_data.get("phone_number")

    def is_confirmation_sent(self):
        return "sms_sent_at" in self.manual_confirmation.other_data

    def render_sms(self, template_context) -> str:
        """Get SMS text for this confirmation."""
        raise NotImplementedError()

    def send_confirmation(self):

        phone_number = self.get_target_phone_number()
        if not phone_number:
            messages.add(self.request, type="error", msg="You do not have phone number set. Please set a phone number before proceeding.")
            return

        context = {
            "sms_code": self.manual_confirmation.other_data["sms_code"],
        }

        sms_text = self.render_sms(context)

        send_sms(self.request, phone_number, sms_text)
        self.manual_confirmation.other_data["sms_sent_at"] = now()

        messages.add(self.request, kind="success", msg="A confirmation SMS has been sent to your phone number {}".format(phone_number), msg_id="msg-phone-confirmation-send")

    def act(self, extra_template_context: dict):
        """Subclasses call this in their own rendering method."""
        request = self.request
        schema = SMSConfirmationSchema().bind(request=request, manual_confirmation=self.manual_confirmation)

        confirm = deform.Button(name='confirm', title="Confirm")
        cancel = deform.Button(name='cancel', title="Cancel")
        form = deform.Form(schema, buttons=(confirm, cancel))

        # If we did not yet send the user SMS do it now
        if not self.is_confirmation_sent():
            self.send_confirmation()

        # User submitted this form
        if request.method == "POST":
            if 'confirm' in request.POST:

                try:
                    appstruct = form.validate(request.POST.items())
                    return self.do_success()
                except deform.ValidationFailure as e:
                    # Render a form version where errors are visible next to the fields,
                    # and the submitted values are posted back
                    rendered_form = e.render()
            elif 'cancel' in request.POST:
                return self.do_cancel()
            else:
                # We don't know which control caused form submission
                raise httpexceptions.HTTPInternalServerError("Unknown form button pressed")
        else:
            # Render a form with initial values
            rendered_form = form.render()

        title = "Create new account"

        template_context = locals()
        template_context.update(extra_template_context)
        return template_context


