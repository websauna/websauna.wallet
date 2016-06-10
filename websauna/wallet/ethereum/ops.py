from pyramid.registry import Registry

from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import CryptoAddressCreation
from .interfaces import IOperationPerformer


def create_address(service: EthereumService, op: CryptoAddressCreation):
    pass


def register_eth_operations(registry: Registry):
    """Register handlers for different crypto operations.

    This maps database rows to functions they should perform in Ethereum service daemon.
    """
    registry.registerAdapter(factory=lambda op: create_address, required=(CryptoAddressCreation,), provided=IOperationPerformer)
