"""Contains synchronous calls to geth daemon."""

from pyramid.registry import Registry

from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import CryptoAddressCreation, CryptoAddressDeposit, CryptoAddressWithdraw
from .interfaces import IOperationPerformer


def create_address(service: EthereumService, op: CryptoAddressCreation):
    """User requests new hosted address.

    We create a hosted wallet contract. The contract id is associated with the user in the database. We hold the the only owner address of the wallet.

    The wallet code is based on https://github.com/ethereum/meteor-dapp-wallet/blob/master/Wallet.sol
    """


def deposit_eth(service: EthereumService, op: CryptoAddressDeposit):
    """This can be settled internally, as we do not have any external communications in this point."""

    # TODO: Wait certain block threshold amount to settle
    op.resolve()
    op.mark_complete()


def withdraw_eth(service: EthereumService, op: CryptoAddressWithdraw):
    pass


def register_eth_operations(registry: Registry):
    """Register handlers for different crypto operations.

    This maps database rows to functions they should perform in Ethereum service daemon.
    """
    registry.registerAdapter(factory=lambda op: create_address, required=(CryptoAddressCreation,), provided=IOperationPerformer)

    registry.registerAdapter(factory=lambda op: withdraw_eth, required=(CryptoAddressWithdraw,), provided=IOperationPerformer)

    registry.registerAdapter(factory=lambda op: deposit_eth, required=(CryptoAddressDeposit,), provided=IOperationPerformer)
