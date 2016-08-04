from pyramid.registry import Registry
from web3 import Web3

from websauna.system.user.models import User
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoAddressDeposit


class CryptoOperationEvent:

    def __init__(self, op: CryptoOperation, registry: Registry, web3: Web3):
        self.op = op
        self.registry = registry
        self.web3 = web3


class CryptoOperationComplete(CryptoOperationEvent):
    pass


class IncomingCryptoDeposit(CryptoOperationEvent):

    def __init__(self, op: CryptoAddressDeposit, registry: Registry, web3: Web3):
        self.op = op
        self.registry = registry
        self.web3 = web3


class InitialAddressCreation:
    """User receives his/her first address in a specific network.

    This happens within the transaction of :class:`websauna.wallet.ethereum.dboperationqueue.OperationQueueManager`.
    """

    def __init__(self, user: User, network: AssetNetwork, op: CryptoOperation, address: CryptoAddress, registry: Registry, web3):
        self.user = user
        self.network = network
        self.op = op
        self.address = address
        self.registry = registry
        self.web3 = web3