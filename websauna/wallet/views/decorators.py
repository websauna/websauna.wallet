from functools import wraps

from pyramid import httpexceptions

from websauna.system.core import messages
from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation



def get_wallet(context):
    # TODO: Move this to its own module
    from websauna.wallet.views.wallet import UserWallet
    while context and not isinstance(context, UserWallet):
        context = context.__parent__

    if not context:
        raise RuntimeError("Could not resolve wallet for {}".format(context))

    return context


def wallet_view(func):
    """Decorates the view to be rendered inside a wallet.

    This view does some pre-traversing checks for having fields to be filled in user profile, etc. If this is the case then redirect the user to a proper view.
    """

    @wraps(func)
    def inner(*args, **kwargs):
        context, request = args
        wallet = get_wallet(context)
        user = request.user

        if not user:
            messages.add(request, kind="warning", msg="Please sign in to view the page.")
            return httpexceptions.HTTPFound(request.route_url("home"))

        # Redirect user to the phone number confirmation
        if request.registry.settings.get("websauna.wallet.require_phone_number"):
            if not UserNewPhoneNumberConfirmation.has_confirmed_phone_number(user):
                return httpexceptions.HTTPFound(request.resource_url(wallet, "new-phone-number"))

        return func(*args, **kwargs)

    return inner

