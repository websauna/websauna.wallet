"""Interaction between geth and database."""
from decimal import Decimal
from pyramid.registry import Registry

from populus.contracts.common import EmptyDataError
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.utils import txid_to_bin, eth_address_to_bin, bin_to_eth_address, to_wei
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import CryptoAddressCreation, CryptoAddressDeposit, CryptoAddressWithdraw, CryptoTokenCreation, CryptoTokenImport, AssetClass, CryptoAddress

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


def create_token(service: EthereumService, op: CryptoTokenCreation):
    """Creates a new token and assigns it ownership to user.

    This takes two transactions

    * One to create the smart contract

    * Other to assign the ownership of all tokens from coinbase to the user
    """

    # Check everyting looks sane
    assert op.crypto_account.id
    assert op.crypto_account.account.id

    asset = op.holding_account.asset
    assert asset.id

    address = bin_to_eth_address(op.crypto_account.address.address)

    # Create Tonex proxy object
    client = service.client
    token = Token.create(client, name=asset.name, symbol=asset.symbol, supply=asset.supply, owner=address)

    # Call geth RPC API over Populus contract proxy
    op.txid = txid_to_bin(token.initial_txid)
    op.block = None
    op.to_address = eth_address_to_bin(token.address)

    # Set information on asset that we have now created and have its smart contract id
    assert not asset.external_id
    asset.external_id = op.to_address


def import_token(service: EthereumService, op: CryptoTokenCreation):
    """Import existing token smart contract as asset."""
    address = bin_to_eth_address(op.to_address)
    token = Token.get(service.client, address)

    network = op.network
    dbsession = service.dbsession
    try:
        name = token.contract.name().decode("utf-8")
        symbol = token.contract.symbol().decode("utf-8")
        supply = Decimal(token.contract.totalSupply())
    except EmptyDataError as e:
        # When we try to access a contract attrib which is not supported by underlying code
        op.mark_failed()
        op.other_data["failure_reason"] = str(e)
        return

    asset = network.create_asset(name=name, symbol=symbol, supply=supply, asset_class=AssetClass.token)
    asset.external_id = op.to_address

    # Fill in balances for the addresses we host
    # TODO: Too much for one transaction
    for caddress in dbsession.query(CryptoAddress).all():

        # Returns 0 for unknown addresses
        try:
            amount = token.contract.balanceOf(bin_to_eth_address(caddress.address))
        except EmptyDataError as e:
            # Bad contract doesn't define balanceOf()
            # This leaves badly imported asset
            op.mark_failed()
            op.other_data["failure_reason"] = str(e)
            return

        if amount > 0:
            account = caddress.get_or_create_account(asset)
            account.account.do_withdraw_or_deposit(Decimal(amount), "Token contract import")

    op.mark_complete()


def register_eth_operations(registry: Registry):
    """Register handlers for different crypto operations.

    This maps database rows to functions they should perform in Ethereum service daemon.
    """

    registry.registerAdapter(factory=lambda op: create_address, required=(CryptoAddressCreation,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: withdraw_eth, required=(CryptoAddressWithdraw,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: deposit_eth, required=(CryptoAddressDeposit,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: create_token, required=(CryptoTokenCreation,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: import_token, required=(CryptoTokenImport,), provided=IOperationPerformer)
