"""See manual confirmation of operations work.."""
from datetime import timedelta

import transaction
from decimal import Decimal

from websauna.utils.time import now
from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import Asset, CryptoOperationState
from websauna.wallet.models import UserCryptoAddress, UserWithdrawConfirmation
from websauna.wallet.models import ManualConfirmationType, ManualConfirmationState, ManualConfirmation


TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"

TEST_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"


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
        confirmation.resolve_sms(code)

        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.resolved
        assert confirmation.user_crypto_operation.crypto_operation.state == CryptoOperationState.waiting



def test_confirm_user_withdraw_cancelled(dbsession, eth_network_id, eth_asset_id, user_id, topped_up_user):
    """User cancels the confirmation."""

    with transaction.manager:
        uca = dbsession.query(UserCryptoAddress).first()
        asset = dbsession.query(Asset).get(eth_asset_id)
        withdraw_op = uca.withdraw(asset, Decimal(5), eth_address_to_bin(TEST_ADDRESS), "Foobar", 1)
        UserWithdrawConfirmation.require_confirmation(withdraw_op)

    with transaction.manager:
        confirmation = dbsession.query(UserWithdrawConfirmation).first()
        confirmation.cancel()

        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.cancelled
        assert confirmation.user_crypto_operation.crypto_operation.state == CryptoOperationState.failed
        assert "error" in confirmation.user_crypto_operation.crypto_operation.other_data


def test_confirm_user_withdraw_timeout(dbsession, eth_network_id, eth_asset_id, user_id, topped_up_user):


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
        assert confirmation.user_crypto_operation.crypto_operation.state == CryptoOperationState.failed
        assert "error" in confirmation.user_crypto_operation.crypto_operation.other_data
