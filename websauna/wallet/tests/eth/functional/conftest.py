from decimal import Decimal

import pytest
import transaction
from websauna.system.user.models import User
from websauna.tests.utils import create_user
from websauna.wallet.ethereum.asset import setup_user_account
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import Asset
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.tests.eth.utils import mock_create_addresses


@pytest.fixture
def require_phone_number(request, registry):
    """Force phone number confirmation on wallet users for the test run."""
    old_val = registry.settings.get("websauna.wallet.require_phone_number", False)
    registry.settings["websauna.wallet.require_phone_number"] = True
    def undo():
        registry.settings["websauna.wallet.require_phone_number"] = old_val
    request.addfinalizer(undo)


@pytest.fixture
def mock_eth_service(eth_network_id, dbsession, registry):
    """Non-functional Ethereum Service without a connection to geth."""

    from web3 import RPCProvider, Web3
    web3 = Web3(RPCProvider("127.0.0.1", 666))
    s = EthereumService(web3, eth_network_id, dbsession, registry)
    return s


@pytest.fixture
def wallet_user(dbsession, registry, mock_eth_service) -> dict:
    """Create a user having a wallet in place with some faux tokens."""

    details = {
        "email": "walletuser@example.com",
        "password": "password"
    }

    with transaction.manager:
        user = create_user(dbsession, registry, email=details["email"], password=details["password"])
        setup_user_account(user, do_mainnet=True)
        details["user_id"] = user.id

    success_op_count, failed_op_count = mock_create_addresses(mock_eth_service, dbsession)

    assert success_op_count == 1
    assert failed_op_count == 0

    return details


@pytest.fixture
def logged_in_wallet_user_browser(dbsession, registry, browser, web_server, wallet_user):
    """Make sure the test browser is logged out as the current user."""

    # Direct Splinter browser to the website
    b = browser
    b.visit(web_server)

    # This link should be in the top navigation
    b.find_by_css("#nav-sign-in").click()

    # Link gives us the login form
    assert b.is_element_present_by_css("#login-form")

    b.fill("username", wallet_user["email"])
    b.fill("password", wallet_user["password"])
    b.find_by_name("login_email").click()

    # After login we see a profile link to our profile
    assert b.is_element_present_by_css("#nav-logout")

    return b


@pytest.fixture
def top_up_user(dbsession, registry, wallet_user, eth_network_id, eth_asset_id):
    """Directly inject some assets to user wallet."""

    with transaction.manager:
        user = dbsession.query(User).get(wallet_user["user_id"])
        setup_user_account(user)

    with transaction.manager:
        user = dbsession.query(User).get(wallet_user["user_id"])
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = dbsession.query(Asset).get(eth_asset_id)
        address = UserCryptoAddress.get_default(user, network)
        account = address.address.get_or_create_account(asset)
        account.account.do_withdraw_or_deposit(Decimal("+10"), "Top up")


@pytest.fixture
def user_phone_number(dbsession, registry, wallet_user):
    """User has phone number set."""

    phone_number = "+1555123124"

    with transaction.manager:
        user = dbsession.query(User).get(wallet_user["user_id"])
        user.user_data["phone_number"] = phone_number

    return phone_number

