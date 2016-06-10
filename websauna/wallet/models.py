"""Place your SQLAlchemy models in this file."""
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



class CryptoOperationType(enum.Enum):

    address = "address"
    create_address = "create_address"
    withdraw = "withdraw"
    deposit = "deposit"


class CryptoOperationState(enum.Enum):
    """Different crypto operations."""

    #: Operation is created by web process and it's waiting to be picked up the service daemon
    waiting = "waiting"

    #: The operation was success
    success = "success"

    #: The operation failed after max retry attempts
    failed = "failed"

    #: The operation was created by the service daemon itself e.g. in the case of incoming funds. This should never fail as these operations cannot be retried as they only write to database and do not communicate with external services.
    immediate = "immediate"


# #
# # class ExternalTransactionOperation(CryptoOperation):
#     """Operation which has one cryptonetwork address."""
#
#     __abstract__ = True
#
#     #: Reverse operation had been generated due to failure
#     external_transaction_id = Column(ForeignKey("external_transaction.id"))
#     external_transaction = relationship("ExternalTransaction", uselist=False, post_update=True)
#
#
# class Deposit(ExternalTransactionOperation):
#
#     __tablename__ = "crypto_operation_deposit"
#     id = Column(UUID(as_uuid=True), ForeignKey('crypto_operation.id'), primary_key=True)
#
#     __mapper_args__ = {
#         'polymorphic_identity': OperationType.deposit,
#     }
#
# class Withdraw(ExternalTransactionOperation):
#
#     __tablename__ = "crypto_operation_withdraw"
#     id = Column(UUID(as_uuid=True), ForeignKey('crypto_operation.id'), primary_key=True)
#
#     __mapper_args__ = {
#         'polymorphic_identity': OperationType.withdraw,
#     }
#
#
# class ExternalTransaction:
#     """Cached state of raw blockchain transaction."""
#     __tablename__ = "external_transaction"
#     id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)
#     txid = Column(String(256), nullable=True)
#
#     network_id = Column(ForeignKey("assetnetwork.id"), nullable=False)
#     network  = relationship(User, primaryjoin=network_id == AssetNetwork.id, backref=backref("assets", uselist=False))
#

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
        return "<A{} ${} OA{} {}>".format(self.id, self.amount, counter_account, self.message)

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


class CryptoAddress(Base):
    """Crypto account is an Ethereum account and Bitcoin address.

    It's target for external crypto operations.

    We only register addresses where private keys are owned by our system.

    Crypto account is only updated by a separate service and all web process write communications with this accout must go through :py:class:`CryptoOperation` async pipeline.
    """

    __tablename__ = "crypto_address"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    #: Native presentation of account / address. Hex string format for Ethereum.
    address = Column(String(256), nullable=True)

    # Network where this operation happens
    network_id = Column(ForeignKey("asset_network.id"), nullable=False)
    network = relationship("AssetNetwork", uselist=False, backref="addresses")


class CryptoAddressAccount(Base):
    """Hold balances of crypto currency or token in address."""

    __tablename__ = "crypto_address_account"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    account_id = Column(ForeignKey("account.id"), nullable=True)
    account = relationship(Account, backref="crypto_address_accounts", uselist=False)

    address_id = Column(ForeignKey("crypto_address.id"), nullable=True)
    address = relationship(CryptoAddress, backref="crypto_address_accounts", uselist=False)


class CryptoOperation(Base):
    """External network operation.

    These operations are not run immediately, but queued to run by a service daemon asynchronously (due to async nature of blockchain). Even if operations complete they can be later shuflfled around e.g. due to blockchain fork.
    """

    __tablename__ = "crypto_operation"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    # Network where this operation happens
    network_id = Column(ForeignKey("asset_network.id"), nullable=False)
    network = relationship("AssetNetwork", uselist=False, backref="operations")

    #: Polymorphic column
    operation_type = Column(Enum(CryptoOperationType), nullable=False)

    #: When this was created
    created_at = Column(UTCDateTime, default=now, nullable=False)

    #: When this data was updated last time
    updated_at = Column(UTCDateTime, onupdate=now)

    #: When this operations was last time attempted to be broadcasted to network.
    #: If the connection to a node is down the operation will be attempted to be rescheduled later.
    attempted_at = Column(UTCDateTime, default=None, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)

    #: When we are created we start in waiting state.
    #: It's up to service daemon to complete the operation and update the state field.
    state = Column(Enum(CryptoOperationState, name="operation_state"), nullable=False, default='waiting')

    # When this operation was completed according to network (when included in block)
    completed_at = Column(UTCDateTime, default=None, nullable=True)

    __mapper_args__ = {
        'polymorphic_on': operation_type,
    }

    def __init__(self, network, **kwargs):
        assert network
        assert network.id
        super().__init__(network=network, **kwargs)


class CryptoAddressOperation(CryptoOperation):
    """Operation which has one cryptonetwork address as source/destination."""

    __tablename__ = "crypto_operation_address"

    id = Column(UUID(as_uuid=True), ForeignKey('crypto_operation.id'), primary_key=True)

    address_id = Column(ForeignKey("crypto_address.id"))
    address = relationship(CryptoAddress,
                           single_parent=True,
                           cascade="all, delete-orphan",
                           primaryjoin=address_id == CryptoAddress.id,
                           backref="user_owned_crypto_accounts")

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.address,
    }

    def __init__(self, address: CryptoAddress):
        assert address
        assert address.id
        assert address.network
        assert address.network.id
        super().__init__(network=address.network)
        self.address = address



class CryptoAddressCreation(CryptoAddressOperation):
    """Create a receiving address.

    Start with null address and store the created address on this SQL row when the node creates a receiving address and has private keys stored within nodes internal storage.
    """

    __tablename__ = "crypto_operation_address_creation"

    id = Column(UUID(as_uuid=True), ForeignKey('crypto_operation_address.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.create_address,
    }

    class MultipleCreationOperations(Exception):
        pass

    def __init__(self, address: CryptoAddress):

        #: TODO: This is application side check that we don't attempt to create wallet side address for an crypto address account twice. E.g. we don't put to creation operations in the pipeline.
        dbsession = Session.object_session(address)
        existing = dbsession.query(CryptoAddressCreation).filter_by(address=address).one_or_none()
        if existing:
            raise CryptoAddressCreation.MultipleCreationOperations("Cannot create address for account twice: {}".format(address))

        super(CryptoAddressCreation, self).__init__(address=address)



class CryptoWithdrawOperation(CryptoAddressOperation):

    __tablename__ = "crypto_operation_withdraw"

    id = Column(UUID(as_uuid=True), ForeignKey('crypto_operation_address.id'), primary_key=True)

    #: If this operation is related to asset this field is referred
    asset_id = Column(ForeignKey("asset.id"), nullable=True)
    asset = relationship(Asset, primaryjoin=asset_id == Asset.id, backref=backref("operations", uselist=False))

    #: The account that sources this operation. In the case of creating address this is the UserOwnedAccount that will receive ethers when the actual node updates the balance on incoming transactions.
    # source_account_id = Column(ForeignKey("account.id"), nullable=True)
    # source_account = relationship(Account, primaryjoin=source_account_id == Account.id, backref="operation_sources", uselist=False)
    #
    # #: If this operation holds its own account where we store the value required for the operation, like reserved ethers to perform a contract write. Using this account ensures we don't double spend internally.
    # holding_account_id = Column(ForeignKey("account.id"), nullable=True)
    # holding_account = relationship(Account, primaryjoin=holding_account_id == Account.id, backref="operation_holdings", uselist=False)


class UserCryptoAddress(object):
    """An account belonging to a some user."""

    __tablename__ = "user_owned_crypto_address"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    address_account_id = Column(ForeignKey("crypto_address_account.id"))
    address_account_id = relationship(CryptoAddressAccount,
                           single_parent=True,
                           cascade="all, delete-orphan",
                           primaryjoin=address_account_id == CryptoAddressAccount.id,
                           backref="user_owned_crypto_addresses")

    user_id = Column(ForeignKey("users.id"), nullable=False)
    user = relationship(User,
                        backref=backref("owned_crypto_addresses",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),)

    @staticmethod
    def create_account(user: User):
        """Initiates account creation operation."""
        dbsession = Session.object_session(user)
        uca = UserCryptoAddress()
        user.owned_crypto_accounts.append(uca)

        dbsession.flush()

        # Put the creation operation in pipeline
        op = CryptoAddressCreation(address=uca.address)
        dbsession.add(op)