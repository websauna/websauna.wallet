"""Accounting primitives for blockchain operations."""

from decimal import Decimal

import binascii
from typing import Optional, Iterable, List

import enum
import uuid

import sqlalchemy
from sqlalchemy import func
from sqlalchemy import Enum
from sqlalchemy import UniqueConstraint
from sqlalchemy import Column, Integer, Numeric, ForeignKey, func, String, LargeBinary
from sqlalchemy.orm import relationship, backref, Session
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy.dialects.postgresql as psql
from websauna.system.model.columns import UTCDateTime
from websauna.system.model.json import NestedMutationDict
from websauna.system.user.models import User
from websauna.utils.time import now
from websauna.system.model.meta import Base
from websauna.wallet.ethereum.utils import bin_to_eth_address
from websauna.wallet.utils import ensure_positive

from .account import Account
from .account import AssetNetwork
from .account import Asset


class MultipleAssetAccountsPerAddress(Exception):
    """Don't allow creation account for the same asset under one address."""


class CryptoOperationType(enum.Enum):
    """What different operations we support."""
    address = "address"
    create_address = "create_address"
    withdraw = "withdraw"
    deposit = "deposit"
    create_token = "create_token"
    import_token = "import_token"
    transaction = "transaction"


class CryptoOperationState(enum.Enum):
    """Different crypto operations."""

    #: Operation is created by web process and it's waiting to be picked up the service daemon
    waiting = "waiting"

    #: Operation has been prepared for broadcast, but we don't know yet if it succeeded
    pending = "pending"

    #: Operation has been broadcasted or received from the network and is waiting for more confirmations
    broadcasted = "broadcasted"

    #: The operation was success, confirmation block count reached
    success = "success"

    #: The operation failed after max retry attempts
    failed = "failed"


class CryptoAddress(Base):
    """Crypto account is an Ethereum account and Bitcoin address.

    It holds multiple different :class:`CryptoAddressAccount` for different asset types.

    It's target for external crypto operations.

    We only register addresses where private keys are owned by our system.

    Crypto account is only updated by a separate service and all web process write communications with this accout must go through :py:class:`CryptoOperation` async pipeline.
    """

    __tablename__ = "crypto_address"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    #: Native presentation of account / address. Hex string format for Ethereum.
    address = Column(LargeBinary(length=20), nullable=True)

    # Network where this operation happens
    network_id = Column(ForeignKey("asset_network.id"), nullable=False)
    network = relationship("AssetNetwork", uselist=False, backref="addresses")

     #: Only one address object per network
    __table_args__ = (UniqueConstraint('network_id', 'address', name='address_per_network'), )

    def __str__(self):
        if self.address:
            return bin_to_eth_address(self.address)
        else:
            return "<no address assigned yet>"

    def __repr__(self):
        return self.__str__()

    def create_account(self, asset: Asset) -> "CryptoAddressAccount":
        """Create an account holding certain asset under this address."""

        # Check validity of this object
        assert self.id
        assert asset
        assert asset.id
        assert self.address

        dbsession = Session.object_session(self)

        if self.crypto_address_accounts.join(Account).join(Asset).filter(Asset.id==asset.id).one_or_none():
            raise MultipleAssetAccountsPerAddress("Tried to create account for asset {} under address {} twice".format(asset, self))

        account = Account(asset=asset)
        dbsession.flush()

        ca_account = CryptoAddressAccount(account=account)
        ca_account.address = self
        dbsession.flush()
        # self.crypto_address_accounts.append(account)

        return ca_account

    def get_account(self, asset: Asset) -> Optional["CryptoAddressAccount"]:
        assert asset.id
        account = self.crypto_address_accounts.join(Account).filter(Account.asset_id==asset.id).one_or_none()
        return account

    def get_or_create_account(self, asset: Asset) -> "CryptoAddressAccount":
        """Creates account for a specific asset on demand."""

        account = self.get_account(asset)
        if account:
            return account

        account = self.create_account(asset)
        # Let's not breed cross network assets accidentally
        assert account.account.asset.network == asset.network
        return account

    def deposit(self, amount: Decimal, asset: Asset, txid: bytes, note: str) -> "CryptoAddressDeposit":
        """External transaction incoming to this address.

        If called twice with the same txid, returns the existing operation, so that we don't process the deposit twice.

        The actual account is credited when this operation is resolved.
        """

        # Check validity of this object
        assert self.id
        assert asset
        assert asset.id
        assert self.address

        assert isinstance(asset, Asset)
        assert type(txid) == bytes

        ensure_positive(amount)

        dbsession = Session.object_session(self)

        crypto_account = self.get_or_create_account(asset)

        # One transaction can contain multiple assets to the same address. Each recognized asset should result to its own operation.
        existing = dbsession.query(CryptoAddressDeposit).filter_by(txid=txid).join(Account).join(Asset).one_or_none()
        if existing:
            return existing

        # Create the operation
        op = CryptoAddressDeposit(network=asset.network)
        op.crypto_account = crypto_account
        op.holding_account = Account(asset=asset)
        op.txid = txid
        dbsession.flush()

        op.holding_account.do_withdraw_or_deposit(amount, note)

        return op

    def create_token(self, asset: Asset, required_confirmation_count:int=1) -> "CryptoTokenCreation":
        """Create a token on behalf of this user."""
        assert asset.id
        assert asset.supply
        assert asset.network.id

        ensure_positive(asset.supply)

        dbsession = Session.object_session(self)

        crypto_account = self.get_or_create_account(asset)

        # One transaction can contain multiple assets to the same address. Each recognized asset should result to its own operation.
        existing = dbsession.query(CryptoTokenCreation).join(CryptoAddressAccount).join(Account).join(Asset).filter(Asset.id==asset.id).one_or_none()
        if existing:
            raise ValueError("Token for this asset already created.")

        # Create the operation
        op = CryptoTokenCreation(network=asset.network)
        op.crypto_account = crypto_account
        op.holding_account = Account(asset=asset)
        dbsession.flush()
        op.holding_account.do_withdraw_or_deposit(asset.supply, "Initial supply")
        op.required_confirmation_count = required_confirmation_count

        return op

    @classmethod
    def get_network_address(self, network: AssetNetwork, address: bytes):
        """Get a hold of address object in a network by symbolic string."""

        assert network.id
        assert address

        dbsession = Session.object_session(network)
        addr = dbsession.query(CryptoAddress).filter_by(network=network, address=address).one_or_none()
        return addr

    def get_account_by_address(self, address: bytes) -> "CryptoAddressAccount":
        """Get account for an asset by its smart contract address."""
        asset = self.network.assets.filter_by(external_id=address).one()
        return self.get_account(asset)

    def get_account_by_symbol(self, symbol: str) -> "CryptoAddressAccount":
        return self.crypto_address_accounts.join(Account).join(Asset).filter_by(symbol=symbol).first()

    @classmethod
    def create_address(self, network: AssetNetwork) -> "CryptoAddressCreation":
        """Initiate operation to create a new address.

        Creates a new address object. Initially address.address is set to null until populated by hosted wallet creation operation.
        """
        assert network.id

        dbsession = Session.object_session(network)
        addr = CryptoAddress(network=network)
        op = CryptoAddressCreation(address=addr)

        dbsession.add(op)
        dbsession.flush()

        return op

    def list_accounts(self) -> List["CryptoAddressAccount"]:
        """Get all accounts registered for this address.

        :return: List of assets registered on this account or empty list if None
        """
        return list(self.crypto_address_accounts)


class CryptoAddressAccount(Base):
    """Hold balances of crypto currency, token or other asset in address.

    This is primarily used to model user holdings in their web wallet. You have one CryptoAddressAccount for ETH, one for each held token.
    """

    __tablename__ = "crypto_address_account"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    account_id = Column(ForeignKey("account.id"), nullable=False)
    account = relationship(Account,
                           uselist=False,
                           backref=backref("crypto_address_accounts",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),)

    address_id = Column(ForeignKey("crypto_address.id"), nullable=False)
    address = relationship(CryptoAddress,
                           uselist=False,
                           backref=backref("crypto_address_accounts",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),)

    def __init__(self, account: Account):
        assert account
        assert account.id
        assert account.asset
        assert account.asset.id
        super().__init__(account=account)

    def __str__(self):
        return "Address:0x{} account:{}".format(binascii.hexlify(self.address.address).decode("utf-8"), self.account)

    def __repr__(self):
        return self.__str__()

    def withdraw(self, amount: Decimal, to_address: bytes, note: str, required_confirmation_count=1) -> "CryptoAddressWithdraw":
        """Initiates the withdraw operation.

        :to_address: External address in binary format where we withdraw

        """

        assert to_address
        assert self.id
        assert self.account
        assert self.account.id
        assert isinstance(amount, Decimal)
        assert isinstance(note, str)

        ensure_positive(amount)

        network = self.account.asset.network
        assert network.id

        op = CryptoAddressWithdraw(network=network)
        op.crypto_account  = self
        op.holding_account = Account(asset=self.account.asset)
        op.external_address = to_address
        op.required_confirmation_count = required_confirmation_count
        dbsession = Session.object_session(self)
        dbsession.add(op)
        dbsession.flush()  # Give ids

        # Lock assetes in transfer to this object
        Account.transfer(amount, self.account, op.holding_account, note)

        return op

    def get_operations(self):
        """List all crypto operations (deposit, withdraw, account creation) related to this account.

        This limits to operations of asset type on this account.
        """
        dbsession = Session.object_session(self)
        return dbsession.query(CryptoOperation)


class CryptoOperation(Base):
    """External network operation.

    These operations are not run immediately, but queued to run by a service daemon asynchronously (due to async nature of blockchain). Even if operations complete they can be later shuflfled around e.g. due to blockchain fork.

    We use SQLAlchemy single table inheritance model here: http://docs.sqlalchemy.org/en/latest/orm/inheritance.html#single-table-inheritance

    State mapping for outgoing operations

    * state is waiting, time is created_at, when operation is put in the queue

    * state is pending, time is performed_at, when operation is prepared for network broadcast. This state is never picked twice, so that we don't accidentally double broadcast withdraws.

    * state is broadcasted, time is broadcasted_at, when operation has gone to geth mempool succesfully and
      we got transaction

    * state is completed, time is completed_at, when confirmation block nums have been reached
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

    #: The operation was prepared for network broadcast
    performed_at = Column(UTCDateTime, default=None, nullable=True)

    #: This operation was succesfully put to geth mempool
    broadcasted_at = Column(UTCDateTime, default=None, nullable=True)

    #: This operation failed completely and cannot be retried
    failed_at = Column(UTCDateTime, default=None, nullable=True)

    #: When this operation reached wanted number of confirmations
    completed_at = Column(UTCDateTime, default=None, nullable=True)

    #: For withdraws we need to address where we are withdrawing to. For deposits store the address where the transfer is coming in.
    external_address = Column(LargeBinary(length=20), nullable=True)

    #: External network transaction id for this column
    txid = Column(LargeBinary(length=32), nullable=True)

    #: Txid - log index pair for incoming tansactions. See get_unique_transction_id()
    opid = Column(LargeBinary(length=34), nullable=True, unique=True)

    #: When this tx was put in blockchain (to calcualte confirmations)
    block = Column(Integer, nullable=True, default=None)

    #: Required blocks confirmation count. If set transaction listener will poll this tx until the required amount reached.
    #: http://ethereum.stackexchange.com/questions/7303/transaction-receipts-blocks-and-confirmations
    required_confirmation_count = Column(Integer, nullable=True, default=None)

    #: Related crypto account
    crypto_account_id = Column(ForeignKey("crypto_address_account.id"), nullable=True)
    crypto_account = relationship(CryptoAddressAccount,
                       uselist=False,
                       backref=backref("crypto_address_transaction_operations",
                                    lazy="dynamic",
                                    cascade="all, delete-orphan",
                                    single_parent=True,),)

    #: Holds the tokens until the operation is transacted to or from the network. In the case of outgoing transfer hold the assets here until the operation is completed, so user cannot send the asset twice. In the case of incoming transfer have a matching account where the assets are being held until the operation is complete.
    holding_account_id = Column(ForeignKey("account.id"), nullable=True)
    holding_account = relationship(Account,
                           uselist=False,
                           backref=backref("crypto_withdraw_holding_accounts",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),)

    #: Any other (subclass specific) data we associate with this transaction. Contains ``error`` string after ``mark_failed()``
    other_data = Column(NestedMutationDict.as_mutable(psql.JSONB), default=dict)

    #: Label used in UI
    human_friendly_type = "<unknown operation>"

    __mapper_args__ = {
        'polymorphic_on': operation_type,
        "order_by": created_at
    }

    def __init__(self, network, **kwargs):
        assert network
        assert network.id
        super().__init__(network=network, **kwargs)

    def __str__(self):
        address = self.external_address and bin_to_eth_address(self.external_address) or "-"
        account = self.crypto_account and self.crypto_account.account or "-"
        failure_reason = self.other_data.get("error") or ""

        return "{} externaladdress:{} completed:{} confirmed:{} failed:{} acc:{} holding: {} network: {}".format(self.operation_type, address, self.completed_at, self.confirmed_at, failure_reason, account, self.holding_account, self.network.name)

    def __repr__(self):
        return self.__str__()

    @property
    def asset_symbol(self) -> Optional[str]:
        """Run human readable asset symbol or None if this operation does not have asset assigned."""
        if self.holding_account:
            return self.holding_account.asset.symbol
        return None

    @property
    def amount(self) -> Optional[Decimal]:
        """Return human readable value of this operation in asset or None if no asset assigned."""
        if self.holding_account:
            return self.holding_account.get_balance()
        return None

    @property
    def confirmed_at(self):
        """Backwards compatibliy."""
        return self.completed_at

    def mark_performed(self):
        """
        Incoming: This operation has been registered to database. It may need more confirmations.

        Outgoing: This operation has been broadcasted to network. It's completion and confirmation might require further network confirmations."""
        self.performed_at = now()
        self.state = CryptoOperationState.pending

    def mark_broadcasted(self):
        """We have reached wanted level of confirmations and scan stop polling this tx now."""
        self.broadcasted_at = now()
        self.state = CryptoOperationState.broadcasted

    def mark_complete(self):
        """This operation is now finalized and there should be no further changes on this operation."""
        self.completed_at = now()
        self.state = CryptoOperationState.success

    def mark_failed(self):
        """This operation cannot be completed."""
        self.failed_at = now()
        self.state = CryptoOperationState.failed

    def update_confirmations(self, confirmation_count) -> bool:
        """How this operation reacts for confirmation counts."""
        raise NotImplementedError()


class CryptoAddressOperation(CryptoOperation):
    """Operation which has one cryptonetwork address as source/destination."""

    address_id = Column(ForeignKey("crypto_address.id"))
    address = relationship(CryptoAddress,
                           single_parent=True,
                           cascade="all, delete-orphan",
                           primaryjoin=address_id == CryptoAddress.id,
                           backref="user_owned_crypto_accounts")

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.address,
        "order_by": CryptoOperation.created_at
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

    #: Label used in UI
    human_friendly_type = "Address creation"

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

    def __str__(self):
        return "<Creating address on network {}>".format(self.network.name)

    def __repr__(self):
        return self.__str__()

class DepositResolver:
    """A confirmation resolver that deposits the user account after certain number of confirmation has passed."""

    def resolve(self):
        """Does the actual debiting on the account."""

        if self.completed_at:
            # We have already (be forced) to complete externally, we can skip this
            return

        incoming_tx = self.holding_account.transactions.one()

        # Settle the user account
        Account.transfer(incoming_tx.amount, self.holding_account, self.crypto_account.account, incoming_tx.message)

        self.mark_complete()

    def update_confirmations(self, confirmation_count) -> bool:
        """Update block since creation of this operation.

        Some operations, esp. deposits are safe to confirm after certain block count after the creation of transactions. This is do avoid forking issues. For example, the general rule for Ether is that all deposits should wait 12 confirmations.

        Some operations do not require confirmation count (create address).

        http://ethereum.stackexchange.com/a/7304/620
        """

        # We are already done
        if self.completed_at:
            return False

        assert self.required_confirmation_count is not None, "update_confirmations() called for non-confirmation count operation"

        if confirmation_count > self.required_confirmation_count:
            self.resolve()
            return True

        return False


class CryptoAddressDeposit(DepositResolver, CryptoOperation):
    """Create a receiving address.

    Start with null address and store the created address on this SQL row when the node creates a receiving address and has private keys stored within nodes internal storage.
    """

    #: Label used in UI
    human_friendly_type = "Deposit"

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.deposit,
    }


class CryptoAddressWithdraw(CryptoOperation):
    """Withdraw assets under user address.

    - Move assets from the source account to a temporary holding account

    - Try broadcast the tx to the network on the next network tick
    """

    #: Label used in UI
    human_friendly_type = "Withdraw"

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.withdraw,
    }


    def update_confirmations(self, confirmation_count) -> bool:
        """Update how many blocks we have got.

        This is only used for tracking confirmation count in UI, it does not have effect for transactions themselves.
        """

        if confirmation_count > self.required_confirmation_count:
            self.mark_complete()
            return True
        return False


class CryptoTokenCreation(DepositResolver, CryptoOperation):
    """Create a token.

    * Set asset information on holding_account for creation information

     * Run ops to get smart contract address

    * Let confirmations to resolve this and credit the initial token supply to owner :class:`CryptoAddressAccount`

    See :meth:`CryptoAddress.create_token`.
    """

    #: Label used in UI
    human_friendly_type = "Token creation"

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.create_token,
    }


class CryptoTokenImport(CryptoOperation):
    """Import an existing smart contract token to the system."""

    #: Label used in UI
    human_friendly_type = "Token import"

    __mapper_args__ = {
        'polymorphic_identity': CryptoOperationType.import_token,
    }


class UserCryptoAddress(Base):
    """An account belonging to a some user."""

    __tablename__ = "user_owned_crypto_address"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    #: User given label for this address
    name = Column(String(256))

    address_id = Column(ForeignKey("crypto_address.id"), nullable=False)
    address = relationship(CryptoAddress,
                           single_parent=True,
                           cascade="all, delete-orphan",
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

    @classmethod
    def get_user_asset_accounts(cls, user: User) -> List[Account]:
        accounts = []
        for address in user.owned_crypto_addresses:
            for account in address.address.list_accounts():
                accounts.append(account)
        return accounts

    @classmethod
    def get_user_asset_accounts_by_network(cls, user: User, network: AssetNetwork) -> List[Account]:
        accounts = []
        for address in user.owned_crypto_addresses.join(CryptoAddress).filter_by(network=network):
            for account in address.address.list_accounts():
                accounts.append(account)
        return accounts

    @classmethod
    def get_default(cls, user: User, network: AssetNetwork, name="Default") -> "UserCryptoAddress":
        address = user.owned_crypto_addresses.filter_by(name=name).join(CryptoAddress).filter_by(network=network).first()
        return address



class UserCryptoOperation(Base):
    """Operation initiated by a user.."""

    __tablename__ = "user_crypto_operation"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=sqlalchemy.text("uuid_generate_v4()"),)

    crypto_operation_id = Column(ForeignKey("crypto_operation.id"), nullable=False, unique=True)
    crypto_operation = relationship(CryptoOperation,
                           single_parent=True,
                           cascade="all, delete-orphan",
                           backref="user_crypto_operations")

    user_id = Column(ForeignKey("users.id"), nullable=False)
    user = relationship(User,
                        backref=backref("owned_crypto_operations",
                                        lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        single_parent=True,),)

    def __str__(self):
        return "<{} {}>".format(self.user, self.crypto_operation)

    def __repr__(self):
        return self.__str__()

    @classmethod
    def get_operations(cls, user: User, states: Iterable) -> Iterable[CryptoOperation]:
        dbsession = Session.object_session(user)
        return dbsession.query(CryptoOperation).filter(CryptoOperation.state.in_(states)).join(UserCryptoOperation).filter_by(user=user)

    @classmethod
    def get_active_operations(cls, user: User) -> Iterable[CryptoOperation]:
        """Get all operations assigned to a user account."""
        states = (CryptoOperationState.waiting, CryptoOperationState.pending)
        return cls.get_operations(user, states)

    @classmethod
    def get_from_op(self, op: CryptoOperation):
        dbsession = Session.object_session(op)
        return dbsession.query(UserCryptoOperation).filter_by(crypto_operation=op).one_or_none()


def import_token(network: AssetNetwork, address: bytes) -> CryptoOperation:
    """Create operation to import existing token smart contract to system as asset.

    :param address: Smart contract address
    """

    assert network.id
    dbsession = Session.object_session(network)

    op = CryptoTokenImport(network=network)
    op.external_address = address
    dbsession.add(op)
    dbsession.flush()
    return op


class CryptoNetworkStatus(Base):
    """Hold uptime/stats about a network."""

    __tablename__ = "crypto_network_status"

    # Network where this operation happens
    network_id = Column(ForeignKey("asset_network.id"), nullable=False, primary_key=True)
    network = relationship("AssetNetwork", uselist=False, backref="crypto_network_status")

    #: Contains keys
    #: * timestamp
    #: * block_number
    data = Column(NestedMutationDict.as_mutable(psql.JSONB), default=dict)

    @classmethod
    def get_network_status(cls, dbsession, network_id: uuid.UUID):
        assert isinstance(network_id, uuid.UUID)
        obj = dbsession.query(CryptoNetworkStatus).get(network_id)
        if not obj:
            obj = CryptoNetworkStatus(network_id=network_id)
            dbsession.add(obj)
            dbsession.flush()
        return obj






