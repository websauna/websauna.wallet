
"""An example login test case."""

import transaction
from pyramid.registry import Registry
from sqlalchemy.orm.session import Session
from splinter.driver import DriverAPI
from websauna.wallet.models import UserWithdrawConfirmation, UserCryptoOperation, CryptoOperation, UserCryptoAddress, Asset
from websauna.wallet.tests.eth.utils import mock_create_addresses


TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"


def test_ui_confirm_withdraw(logged_in_wallet_user_browser: DriverAPI, dbsession: Session, user_phone_number, top_up_user, eth_asset_id):
    """Create new account through UI."""
    # Go to address
    b = logged_in_wallet_user_browser
    b.find_by_css("#nav-wallet").click()
    b.find_by_css("#row-asset-{} a.withdraw-asset".format(eth_asset_id)).click()

    b.fill("address", TEST_ADDRESS)
    b.fill("amount", "0.1")
    b.find_by_css("button[name='process']").click()

    # We should arrive to the confirmation page
    assert b.is_element_present_by_css("#heading-confirm-withdraw")

    # Peek into SMS code
    with transaction.manager:
        # Withdraw is the firt user op on the stack
        withdraw = dbsession.query(UserCryptoOperation).join(CryptoOperation).order_by(CryptoOperation.created_at.desc()).first()
        confirmation = UserWithdrawConfirmation.get_pending_confirmation(withdraw)
        sms_code = confirmation.other_data["sms_code"]

    b.fill("code", sms_code)
    b.find_by_css("button[name='confirm']").click()

    # We got text box telling withdraw was success
    assert b.is_element_present_by_css("#msg-withdraw-confirmed")


def test_ui_confirm_withdraw_advanced(logged_in_wallet_user_browser: DriverAPI, dbsession: Session, user_phone_number, top_up_user, eth_asset_id):
    """Create new account through UI."""
    # Go to address
    b = logged_in_wallet_user_browser
    b.find_by_css("#nav-wallet").click()
    b.find_by_css("#row-asset-{} a.withdraw-asset".format(eth_asset_id)).click()

    b.fill("address", TEST_ADDRESS)
    b.fill("amount", "0.1")

    b.find_by_css(".deform-collapse-heading a").click()
    assert b.is_element_visible_by_css("input[name='gas']")
    b.fill("gas", 1000000)
    b.fill("data", "0x123456")

    b.find_by_css("button[name='process']").click()

    # We should arrive to the confirmation page
    assert b.is_element_present_by_css("#heading-confirm-withdraw")

    # Peek into SMS code
    with transaction.manager:
        # Withdraw is the firt user op on the stack
        withdraw = dbsession.query(UserCryptoOperation).join(CryptoOperation).order_by(CryptoOperation.created_at.desc()).first()

        assert withdraw.crypto_operation.other_data["gas"] == 1000000
        assert withdraw.crypto_operation.other_data["data"] == "0x123456"


def test_ui_cancel_withdraw(logged_in_wallet_user_browser: DriverAPI, dbsession: Session, user_phone_number, top_up_user, eth_asset_id):
    """Create new account through UI."""

    # Record balance before cancel
    with transaction.manager:
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        original_balance = uca.get_crypto_account(asset).account.get_balance()

    # Go to address
    b = logged_in_wallet_user_browser
    b.find_by_css("#nav-wallet").click()
    b.find_by_css("#row-asset-{} a.withdraw-asset".format(eth_asset_id)).click()

    b.fill("address", TEST_ADDRESS)
    b.fill("amount", "0.1")
    b.find_by_css("button[name='process']").click()

    # We should arrive to the confirmation page
    assert b.is_element_present_by_css("#heading-confirm-withdraw")

    b.find_by_css("button[name='cancel']").click()

    # We got text box telling withdraw was cancelled
    assert b.is_element_present_by_css("#msg-withdraw-cancelled")

    # Balance should be back to original
    with transaction.manager:
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        assert original_balance == uca.get_crypto_account(asset).account.get_balance()








