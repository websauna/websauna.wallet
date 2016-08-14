from functools import wraps

from pyramid import httpexceptions

from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation


def wallet_view(func):
    """Decorates the view to be rendered inside a wallet.

    This view does some pre-traversing checks for having fields to be filled in user profile, etc. If this is the case then redirect the user to a proper view.
    """

    @wraps(func)
    def inner(*args, **kwargs):
        wallet, request = args
        user = request.user

        # Redirect user to the phone number confirmation
        if request.registry.settings.get("websauna.wallet.require_phone_number"):
            if not UserNewPhoneNumberConfirmation.has_confirmed_phone_number(user):
                return httpexceptions.HTTPFound(request.resource_url(wallet, "new-phone-number"))

        return func(*args, **kwargs)

    return inner

