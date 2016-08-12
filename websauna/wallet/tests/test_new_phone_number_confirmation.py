"""See manual confirmation of operations work.."""
from datetime import timedelta

import pytest
import transaction

from websauna.system.user.models import User
from websauna.tests.utils import create_user
from websauna.wallet.models import ManualConfirmationType, ManualConfirmationState
from websauna.wallet.models.confirmation import UserNewPhoneNumberConfirmation


@pytest.fixture()
def user_id(dbsession, registry):
    """Create a sample user."""
    with transaction.manager:
        user = create_user(dbsession, registry)
        return user.id


def test_confirm_user_phone_number_success(dbsession, user_id):
    """SMS confirmation success."""

    # Prepare confirmation
    with transaction.manager:
        user = dbsession.query(User).get(user_id)
        confirmation = UserNewPhoneNumberConfirmation.require_confirmation(user, "+15551231234")
        assert confirmation.created_at
        assert confirmation.confirmation_type == ManualConfirmationType.sms
        assert confirmation.state == ManualConfirmationState.pending
        assert UserNewPhoneNumberConfirmation.get_pending_confirmation(user)

    # Resolve confirmation and see user gets a phone number
    with transaction.manager:
        user = dbsession.query(User).get(user_id)
        confirmation = dbsession.query(UserNewPhoneNumberConfirmation).first()
        code = confirmation.other_data["sms_code"]
        confirmation.resolve_sms(code, None)

        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.resolved
        assert user.user_data["phone_number"] == "+15551231234"
        assert not UserNewPhoneNumberConfirmation.get_pending_confirmation(user)


def test_confirm_user_phone_number_cancel(dbsession, user_id):
    """SMS confirmation success."""

    # Prepare confirmation
    with transaction.manager:
        user = dbsession.query(User).get(user_id)
        confirmation = UserNewPhoneNumberConfirmation.require_confirmation(user, "+15551231234")
        assert confirmation.created_at
        assert confirmation.confirmation_type == ManualConfirmationType.sms
        assert confirmation.state == ManualConfirmationState.pending
        assert UserNewPhoneNumberConfirmation.get_pending_confirmation(user)

    # Resolve confirmation and see user gets a phone number
    with transaction.manager:
        user = dbsession.query(User).get(user_id)
        confirmation = dbsession.query(UserNewPhoneNumberConfirmation).first()
        confirmation.cancel()

        assert confirmation.action_taken_at
        assert confirmation.state == ManualConfirmationState.cancelled
        assert "phone_number" not in user.user_data
        assert not UserNewPhoneNumberConfirmation.get_pending_confirmation(user)

