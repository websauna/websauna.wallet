import transaction
from sqlalchemy.orm.session import Session

from pyramid_sms.utils import get_sms_backend
from splinter.driver import DriverAPI
from websauna.system.user.models import User
from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation



def test_ui_confirm_phone_number(require_phone_number, logged_in_wallet_user_browser: DriverAPI, dbsession: Session, mock_eth_service, test_request):
    """User needs a confirmed phone number before entering the wallet."""

    # Run functional tests against a Waitress web server running in another thread
    b = logged_in_wallet_user_browser
    b.find_by_css("#nav-wallet").click()

    assert b.is_element_present_by_css("#heading-new-phone-number")
    b.fill("phone_number", "+15551231234")
    b.find_by_css("button[type='submit']").click()

    # We arrived to SMS code verification page
    assert b.is_element_present_by_css("#heading-confirm-phone-number")

    # We have a notification that SMS code was sent
    assert b.is_element_present_by_css("#msg-phone-confirmation-send")

    # Peek into SMS code
    with transaction.manager:
        user = dbsession.query(User).first()
        confirmation = UserNewPhoneNumberConfirmation.get_pending_confirmation(user)
        sms_code = confirmation.other_data["sms_code"]

    # Get a dummy SMS backend that's configured in test fixtures
    backend = get_sms_backend(test_request)

    # Make sure code got out to the user
    msg = backend.get_last_message()
    assert sms_code in msg

    # Enter the code
    b.fill("code", sms_code)
    b.find_by_css("button[type='submit']").click()

    # We arrived to wallet overview
    assert b.is_element_present_by_css("#heading-wallet-overview")

    # We have a notification for phone number verified
    assert b.is_element_present_by_css("#msg-phone-confirmed")


def test_ui_invalid_phone_confirmation_code(require_phone_number, logged_in_wallet_user_browser: DriverAPI, dbsession: Session, mock_eth_service, test_request):
    """User needs a     confirmed phone number before entering the wallet."""

    # Run functional tests against a Waitress web server running in another thread
    b = logged_in_wallet_user_browser
    b.find_by_css("#nav-wallet").click()

    assert b.is_element_present_by_css("#heading-new-phone-number")
    b.fill("phone_number", "+15551231234")
    b.find_by_css("button[type='submit']").click()

    # We arrived to SMS code verification page
    assert b.is_element_present_by_css("#heading-confirm-phone-number")

    # We have a notification that SMS code was sent
    assert b.is_element_present_by_css("#msg-phone-confirmation-send")

    # Cancel action
    b.find_by_css("button[name='cancel']").click()

    # We are back to where new phone number is required
    assert b.is_element_present_by_css("#heading-new-phone-number")

