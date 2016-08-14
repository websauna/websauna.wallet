import random
from string import digits
from typing import Optional

import datetime
from sqlalchemy.orm import Session

import enum

import sqlalchemy as sa
from sqlalchemy import orm
import sqlalchemy.dialects.postgresql as psql

from websauna.system.model.columns import UTCDateTime
from websauna.system.model.json import NestedMutationDict
from websauna.system.user.models import User
from websauna.system.model.meta import Base
from websauna.utils.time import now


def create_sms_code():
    return "".join([random.choice(digits) for i in range(6)])


class ManualConfirmationState(enum.Enum):
    pending = "pending"
    resolved = "resolved"
    cancelled = "cancelled"
    timed_out = "timed_out"


class ManualConfirmationType(enum.Enum):

    #: User prompted for password
    password = "password"

    #: Email confirmation send to the user
    email = "email"

    #: Six digits send via SMS to the user
    sms = "sms"

    #: Manual admin intervention
    admin = "admin"

    #: Two factor token required
    two_factor = "two_factor"



class ManualConfirmationError(Exception):
    pass


class ManualConfirmation(Base):

    __tablename__ = "manual_confirmation"

    id = sa.Column(psql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()"),)

    #: When this was created
    created_at = sa.Column(UTCDateTime, default=now, nullable=False)

    #: When this data was updated last time
    updated_at = sa.Column(UTCDateTime, onupdate=now)

    user_id = sa.Column(sa.ForeignKey("users.id"), nullable=False)
    user = orm.relationship(User,
                        backref=orm.backref("manual_confirmations",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),)

    confirmation_type = sa.Column(sa.Enum(ManualConfirmationType), nullable=False)

    state = sa.Column(sa.Enum(ManualConfirmationState), nullable=False, default=ManualConfirmationState.pending)

    confirmed_action = sa.Column(sa.String(32))

    #: How much time we have before we time out
    deadline_at = sa.Column(UTCDateTime, nullable=False)

    #: When user or timeout mechanism took this out
    action_taken_at = sa.Column(UTCDateTime, nullable=True)

    #: Any other data, like sent out SMS confirmation code
    #: Contains backref
    other_data = sa.Column(NestedMutationDict.as_mutable(psql.JSONB), default=dict)

    __mapper_args__ = {
        'polymorphic_identity': 'manual_confirmation',
        'polymorphic_on': confirmed_action
    }

    def require_sms(self, phone_number):
        """Require SMS confirmation as confirmation type."""
        self.confirmation_type = ManualConfirmationType.sms
        self.other_data = dict(sms_code=create_sms_code(), phone_number=phone_number)

    def is_valid_sms(self, code):
        return self.other_data["sms_code"] == code

    def resolve_sms(self, code, capture_data: Optional[dict]):

        if self.confirmation_type != ManualConfirmationType.sms:
            raise ManualConfirmationError("Wrong manual confirmation type")

        if not self.is_valid_sms(code):
            raise ManualConfirmationError("SMS does not match")

        self.resolve(capture_data)

    def update_capture_data(self, capture_data: Optional[dict]):
        if capture_data:
            self.other_data.update(capture_data)

    def resolve(self, capture_data: Optional[dict]=None):

        if now() > self.deadline_at:
            raise ManualConfirmationError("Cannot confirm after deadline.")

        self.action_taken_at = now()
        self.state = ManualConfirmationState.resolved

        self.update_capture_data(capture_data)

    def cancel(self, capture_data: Optional[dict]=None):
        self.action_taken_at = now()
        self.state = ManualConfirmationState.cancelled
        self.update_capture_data(capture_data)

    def timeout(self):
        self.action_taken_at = now()
        self.state = ManualConfirmationState.timed_out

    @classmethod
    def run_timeout_checks(cls, dbsession, now):
        for confirmation in dbsession.query(ManualConfirmation).filter_by(state=ManualConfirmationState.pending):
            if now > confirmation.deadline_at:
                confirmation.timeout()


class UserNewPhoneNumberConfirmation(ManualConfirmation):
    """Manage user phone number initial set and phone number change confirmations."""

    __tablename__ = "user_new_phone_number_confirmation"

    id = sa.Column(psql.UUID(as_uuid=True), sa.ForeignKey("manual_confirmation.id"), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': 'new_phone_number',
    }

    def resolve(self, capture_data: Optional[dict]=None):
        super(UserNewPhoneNumberConfirmation, self).resolve(capture_data)
        self.user.user_data["phone_number"] = self.other_data["phone_number"]

    @classmethod
    def has_confirmed_phone_number(cls, user: User) -> bool:
        return "phone_number" in user.user_data

    @classmethod
    def get_pending_confirmation(cls, user: User) -> Optional["UserNewPhoneNumberConfirmation"]:
        dbsession = Session.object_session(user)
        return dbsession.query(UserNewPhoneNumberConfirmation).filter_by(user=user, state=ManualConfirmationState.pending).one_or_none()

    @classmethod
    def require_confirmation(cls, user: User, phone_number, timeout=4*3600):
        assert cls.get_pending_confirmation(user) == None
        dbsession = Session.object_session(user)

        confirmation = UserNewPhoneNumberConfirmation()
        confirmation.user = user
        confirmation.deadline_at = now() + datetime.timedelta(seconds=timeout)
        confirmation.require_sms(phone_number)
        dbsession.add(confirmation)
        dbsession.flush()
        return confirmation
