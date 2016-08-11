
"""An example login test case."""

import transaction
from pyramid.registry import Registry
from sqlalchemy.orm.session import Session
from splinter.driver import DriverAPI
from websauna.wallet.tests.eth.utils import mock_create_addresses


def test_ui_create_address(logged_in_wallet_user_browser: DriverAPI, dbsession: Session, mock_eth_service):
    """Create new account through UI."""

    b = logged_in_wallet_user_browser
    b.find_by_css("#nav-wallet").click()
    b.find_by_css("#nav-wallet-accounts").click()
    b.find_by_css("#btn-create-account").click()
    b.fill("name", "Foboti")
    b.find_by_css("button[type='submit']").click()

    # Now in transaction list page
    assert b.is_element_present_by_css("#msg-account-created")

    # Pick the freshly created account for the transaction list
    rows = b.find_by_css(".row-operation")
    rows[0].find_by_css("a")[0].click()

    assert b.is_element_present_by_css("#heading-op")  # Page renders without errors
    assert b.is_element_present_by_css("#op-state-waiting")  # Op has not run yet

    # Create the account
    mock_create_addresses(mock_eth_service, dbsession, address="0x7C0d52faAB596C08F484E3478AeBc6205F3f5D8C")

    # Reload the page
    b.visit(b.url)

    # All details filled in
    assert b.is_element_present_by_css("#heading-op")  # Page renders without errors
    assert b.is_element_present_by_css("#op-state-success")  # Op complete

    # View address
    b.find_by_css("#nav-op-address").click()
    assert b.is_element_present_by_css("#heading-address")  # Page renders without errors











