"""Contains synchronous calls to geth daemon."""

from pyramid.registry import Registry

from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import txid_to_bin, eth_address_to_bin, bin_to_eth_address, to_wei
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import CryptoAddressCreation, CryptoAddressDeposit, CryptoAddressWithdraw
from .interfaces import IOperationPerformer


def create_address(service: EthereumService, op: CryptoAddressCreation):
    """User requests new hosted address.

    We create a hosted wallet contract. The contract id is associated with the user in the database. We hold the the only owner address of the wallet.

    The wallet code is based on https://github.com/ethereum/meteor-dapp-wallet/blob/master/Wallet.sol
    """

    client = service.client
    wallet = HostedWallet.create(client)
    txid = wallet.initial_txid
    receipt = client.get_transaction_receipt(txid)

    op.txid = txid_to_bin(txid)
    op.block = int(receipt["blockNumber"], 16)
    op.address.address = eth_address_to_bin(wallet.address)

    op.mark_complete()


def deposit_eth(service: EthereumService, op: CryptoAddressDeposit):
    """This can be settled internally, as we do not have any external communications in this point."""
    op.resolve()
    op.mark_complete()


def withdraw_eth(service: EthereumService, op: CryptoAddressWithdraw):
    """Perform withdraw operation from the wallet."""

    # Check everyting looks sane
    assert op.crypto_account.id
    assert op.crypto_account.account.id
    assert op.holding_account.id
    assert op.holding_account.get_balance() > 0
    assert op.to_address
    assert op.required_confirmation_count  # Should be set by the creator

    address = bin_to_eth_address(op.crypto_account.address.address)

    # How much we are withdrawing
    amount = op.holding_account.transactions.one().amount

    client = service.client
    wallet = HostedWallet.get(client, address)

    # Call geth RPC API over Populus contract proxy
    txid = wallet.withdraw(bin_to_eth_address(op.to_address), amount)

    # Fill in details.
    # Block number will be filled in later, when confirmation updater picks a transaction receipt for this operation.
    op.txid = txid_to_bin(txid)
    op.block = None
    op.mark_complete()  # This cannot be cancelled


def register_eth_operations(registry: Registry):
    """Register handlers for different crypto operations.

    This maps database rows to functions they should perform in Ethereum service daemon.
    """

    registry.registerAdapter(factory=lambda op: create_address, required=(CryptoAddressCreation,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: withdraw_eth, required=(CryptoAddressWithdraw,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: deposit_eth, required=(CryptoAddressDeposit,), provided=IOperationPerformer)
