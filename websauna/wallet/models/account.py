"""Core accounting primitivtes."""
from decimal import Decimal
import enum

import sqlalchemy
from sqlalchemy import func
from sqlalchemy import Enum
from sqlalchemy import Column, Integer, Numeric, ForeignKey, func, String
from sqlalchemy import CheckConstraint
from sqlalchemy.orm import relationship, backref, Session
from sqlalchemy.dialects.postgresql import UUID
from websauna.system.model.columns import UTCDateTime
from websauna.system.user.models import User
from websauna.utils.time import now
from websauna.system.model.meta import Base


class AssetNetwork(Base):
    __tablename__ = "asset_network"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)
    name = Column(String(256), nullable=False)
    assets = relationship("Asset", lazy="dynamic", back_populates="network")


class AssetFormat(Enum):
    """What's preferred display format for this asset."""

    #: 0,00
    fiat = 1

    #: 100.000,000,000
    cryptocurrency = 2

    #: 10.000
    tokens = 3


class Asset(Base):

    __tablename__ = "asset"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    #: When this was created
    created_at = Column(UTCDateTime, default=now, nullable=False)

    #: When this data was updated last time
    updated_at = Column(UTCDateTime, onupdate=now)

    network_id = Column(ForeignKey("asset_network.id"), nullable=False)
    network  = relationship("AssetNetwork", uselist=False, back_populates="assets")

    #: Human readable name of this asset. Cannot be unique, because there can be several independent token contracts with the same asset name.
    name = Column(String(256), nullable=True, default=None, unique=False)

    #: Stock like symbol of the asset.
    symbol = Column(String(32), nullable=True, default=None, unique=False)

    #: The id of the asset in its native network
    external_id = Column(String(256), nullable=True, default=None)

    asset_format = Column(Integer, nullable=False, server_default="0")

    def get_local_liabilities(self):
        """Get sum how much assets we are holding on all of our accounts."""
        dbsession = Session.object_session(self)
        asset_total = dbsession.query(func.sum(Account.denormalized_balance)).join(Asset).scalar()
        return asset_total


class Account(Base):
    """Internal credit/debit account.

    Accounts can be associated with user, escrow, etc. They offer simple but robust account-to-account transfer mechanisms.s
    """
    __tablename__ = "account"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    #: When this was created
    created_at = Column(UTCDateTime, default=now, nullable=False)

    #: When this data was updated last time
    updated_at = Column(UTCDateTime, onupdate=now)

    asset_id = Column(ForeignKey("asset.id"), nullable=False)
    asset = relationship(Asset, backref=backref("accounts", uselist=True, lazy="dynamic"))

    denormalized_balance = Column(Numeric(40, 10), nullable=False, server_default='0')

    class BalanceException(Exception):
        pass

    def __str__(self):
        return "<Acc {}>".format(self.id)

    def __repr__(self):
        return self.__str__()

    def get_balance(self):
        # denormalized balance can be non-zero until the account is created
        return self.denormalized_balance or Decimal(0)

    def update_balance(self) -> Decimal:
        assert self.id
        dbsession = Session.object_session(self)
        results = dbsession.query(func.sum(AccountTransaction.amount.label("sum"))).filter(AccountTransaction.account_id == self.id).all()
        self.denormalized_balance = results[0][0] if results else Decimal(0)

    def do_withdraw_or_deposit(self, amount: Decimal, note: str, allow_negative: bool=False) -> "AccountTransaction":
        """Do a top up operation on account.

        This operation does not have matching credit/debit transaction on any account. It's main purpose is to initialize accounts with certain balance.

        :param amount: How much
        :param note: Human readable
        :param allow_negative: Set true to create negative balances or allow overdraw.
        :raise Account.BalanceException: If the account is overdrawn
        :return: Created AccountTransaction
        """

        assert self.id
        assert isinstance(amount, Decimal)

        if not allow_negative:
            if amount < 0 and self.get_balance() < abs(amount):
                raise Account.BalanceException("Cannot withdraw more than you have on the account")

        DBSession = Session.object_session(self)
        t = AccountTransaction(account=self)
        t.amount = Decimal(amount)
        t.message = note
        DBSession.add(t)

        self.update_balance()

        return t

    @classmethod
    def transfer(self, amount:Decimal, from_:object, to:object, note:str, registry=None):
        """Transfer between accounts"""
        DBSession = Session.object_session(from_)
        withdraw = from_.do_withdraw_or_deposit(-amount, note)
        deposit = to.do_withdraw_or_deposit(amount, note)
        DBSession.flush()

        deposit.counterparty = withdraw
        withdraw.counterparty = deposit


class AccountTransaction(Base):
    """Instant transaction between accounts."""

    __tablename__ = "account_transaction"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    #: When this was created
    created_at = Column(UTCDateTime, default=now, nullable=False)

    #: When this data was updated last time
    updated_at = Column(UTCDateTime, onupdate=now, nullable=True)

    account_id = Column(ForeignKey("account.id"))
    account = relationship(Account,
                           primaryjoin=account_id == Account.id,
                           backref=backref("transactions",
                                            lazy="dynamic",
                                            cascade="all, delete-orphan",
                                            single_parent=True,
                                            ))

    amount = Column(Numeric(40, 10), nullable=False, server_default='0')
    message = Column(String(256))

    counterparty_id = Column(ForeignKey("account_transaction.id"))
    counterparty = relationship("AccountTransaction", primaryjoin=counterparty_id == id, uselist=False, post_update=True)

    def __str__(self):
        counter_account = self.counterparty.account if self.counterparty else "-"
        return "<ATX{} ${} FROM:{} TO:{} {}>".format(self.id, self.amount, self.account, counter_account, self.message)

    def __repr__(self):
        return self.__str__()

    def __json__(self, request):
        return dict(id=str(self.id), amount=float(self.amount), message=self.message)


class UserOwnedAccount(Base):
    """An account belonging to a some user."""

    __tablename__ = "user_owned_account"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    account_id = Column(ForeignKey("account.id"))
    account = relationship(Account,
                           single_parent=True,
                           cascade="all, delete-orphan",
                           primaryjoin=account_id == Account.id,
                           backref="user_owned_accounts")

    user_id = Column(ForeignKey("users.id"), nullable=False)
    user = relationship(User,
                        backref=backref("owned_accounts",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),
                        uselist=False)

    name = Column(String(256), nullable=True)

    @classmethod
    def create_for_user(cls, user, asset):
        dbsession = Session.object_session(user)
        account = Account(asset=asset)
        dbsession.flush()
        uoa = UserOwnedAccount(user=user, account=account)
        return uoa

    @classmethod
    def get_or_create_user_default_account(cls, user, asset: Asset):
        dbsession = Session.object_session(user)
        account = user.owned_accounts.join(Account).filter(Account.asset == asset).first()

        # We already have an account for this asset
        if account:
            return account, False
        dbsession.flush()

        # TODO: Why cannot use relationship here
        account = Account(asset_id=asset.id)  # Create account
        dbsession.add(account)
        dbsession.flush()
        uoa = UserOwnedAccount(user=user, account=account)  # Assign it to a user
        dbsession.flush()  # Give id to UserOwnedAccount
        return uoa, True