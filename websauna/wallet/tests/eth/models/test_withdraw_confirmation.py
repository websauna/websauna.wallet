"""See manual confirmation of operations work.."""
from datetime import timedelta

import pytest
import transaction
from decimal import Decimal

from websauna.tests.utils import create_user
from websauna.utils.time import now
from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import Asset, CryptoOperationState
from websauna.wallet.models import UserCryptoAddress, UserWithdrawConfirmation
from websauna.wallet.models import ManualConfirmationType, ManualConfirmationState, ManualConfirmation


TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"


@pytest.fixture()
def user_id(dbsession, registry):
    """Create a sample user."""
    with transaction.manager:
        user = create_user(dbsession, registry)
        user.user_data["phone_number"] = "+15551231234"
        return user.id


def test_confirm_user_withdraw_success(dbsession, eth_network_id, eth_asset_id, user_id, topped_up_user):
    """SMS confirmation success."""

    with transaction.manager:
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        withdraw_op = uca.withdraw(asset, Decimal(5), eth_address_to_bin(TEST_ADDRESS), "Foobar", 1)
        confirmation = UserWithdrawConfirmation.require_confirmation(withdraw_op)
        assert confirmation.created_at
        assert confirmation.confirmation_type == ManualConfirmationType.sms
        assert confirmation.state == ManualConfirmationState.pending

    with transaction.manager:
        confirmation = dbsession.query(UserWithdrawConfirmation).first()
        code = confirmation.other_data["sms_code"]
        confirmation.resolve_sms(code, None)

        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.resolved
        assert confirmation.user_crypto_operation.crypto_operation.state == CryptoOperationState.waiting



def test_confirm_user_withdraw_cancelled(dbsession, eth_network_id, eth_asset_id, user_id, topped_up_user):
    """User cancels the withdraw confirmation."""

    with transaction.manager:
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        original_balance = uca.get_crypto_account(asset).account.get_balance()

        withdraw_op = uca.withdraw(asset, Decimal(7), eth_address_to_bin(TEST_ADDRESS), "Foobar", 1)
        UserWithdrawConfirmation.require_confirmation(withdraw_op)

    with transaction.manager:
        confirmation = dbsession.query(UserWithdrawConfirmation).first()
        confirmation.cancel()

        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.cancelled
        assert confirmation.user_crypto_operation.crypto_operation.state == CryptoOperationState.cancelled
        assert "error" in confirmation.user_crypto_operation.crypto_operation.other_data

        # The balance was restored
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        assert uca.get_crypto_account(asset).account.get_balance() == original_balance


def test_confirm_user_withdraw_timeout(dbsession, eth_network_id, eth_asset_id, user_id, topped_up_user):
    """User did not reply to withdraw confirmation within the timeout."""
    with transaction.manager:
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        withdraw_op = uca.withdraw(asset, Decimal(5), eth_address_to_bin(TEST_ADDRESS), "Foobar", 1)
        UserWithdrawConfirmation.require_confirmation(withdraw_op)

    with transaction.manager:
        ManualConfirmation.run_timeout_checks(dbsession, now() + timedelta(hours=12))

    with transaction.manager:
        confirmation = dbsession.query(UserWithdrawConfirmation).first()
        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.timed_out
        assert confirmation.user_crypto_operation.crypto_operation.state == CryptoOperationState.cancelled
        assert "error" in confirmation.user_crypto_operation.crypto_operation.other_data
