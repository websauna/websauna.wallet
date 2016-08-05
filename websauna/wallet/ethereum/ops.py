"""Interaction between geth and database."""
from decimal import Decimal
import logging

import eth_abi
from pyramid.registry import Registry
from sqlalchemy.orm import Session

from web3 import Web3

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.utils import txid_to_bin, eth_address_to_bin, bin_to_eth_address, to_wei
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import CryptoAddressCreation, CryptoAddressDeposit, CryptoAddressWithdraw, CryptoTokenCreation, CryptoTokenImport, AssetClass, CryptoAddress

from .interfaces import IOperationPerformer


logger = logging.getLogger(__name__)


def create_address(web3: Web3, dbsession: Session, op: CryptoAddressCreation):
    """User requests new hosted address.

    We create a hosted wallet contract. The contract id is associated with the user in the database. We hold the the only owner address of the wallet.

    The wallet code is based on https://github.com/ethereum/meteor-dapp-wallet/blob/master/Wallet.sol
    """

    print("Session 1", Session.object_session(op))
    print("Session 2", Session.object_session(op.address))

    wallet = HostedWallet.create(web3)
    txid = wallet.initial_txid
    receipt = web3.eth.getTransactionReceipt(txid)

    op.txid = txid_to_bin(txid)
    op.block = receipt["blockNumber"]
    op.address.address = eth_address_to_bin(wallet.address)
    op.external_address = op.address.address

    op.mark_performed()
    op.mark_complete()


def deposit_eth(web3: Web3, dbsession: Session, op: CryptoAddressDeposit):
    """This can be settled internally, as we do not have any external communications in this point."""
    op.resolve()
    op.mark_performed()
    op.mark_complete()


def withdraw_eth(web3: Web3, dbsession: Session, op: CryptoAddressWithdraw):
    """Perform ETH withdraw operation from the wallet."""

    # Check everyting looks sane
    assert op.crypto_account.id
    assert op.crypto_account.account.id
    assert op.holding_account.id
    assert op.holding_account.get_balance() > 0
    assert op.external_address
    assert op.required_confirmation_count  # Should be set by the creator

    address = bin_to_eth_address(op.crypto_account.address.address)

    # How much we are withdrawing
    amount = op.holding_account.transactions.one().amount

    wallet = HostedWallet.get(web3, address)

    # Call geth RPC API over Populus contract proxy
    txid = wallet.withdraw(bin_to_eth_address(op.external_address), amount)

    # Fill in details.
    # Block number will be filled in later, when confirmation updater picks a transaction receipt for this operation.
    op.txid = txid_to_bin(txid)
    op.block = None

    op.mark_performed()
    op.mark_complete()  # This cannot be cancelled


def withdraw_token(web3: Web3, dbsession: Session, op: CryptoAddressWithdraw):
    """Perform token withdraw operation from the wallet."""

    # Check everyting looks sane
    assert op.crypto_account.id
    assert op.crypto_account.account.id
    assert op.holding_account.id
    assert op.holding_account.get_balance() > 0
    assert op.external_address
    assert op.required_confirmation_count  # Should be set by the creator
    asset = op.holding_account.asset
    assert asset.asset_class == AssetClass.token

    from_address = bin_to_eth_address(op.crypto_account.address.address)
    to_address = bin_to_eth_address(op.external_address)
    asset_address = bin_to_eth_address(asset.external_id)

    # How much we are withdrawing
    amount = op.holding_account.transactions.one().amount

    wallet = HostedWallet.get(web3, from_address)
    token = Token.get(web3, asset_address)

    amount = token.validate_transfer_amount(amount)

    # Call geth RPC API over Populus contract proxy
    txid = wallet.execute(token.contract, "transfer", [to_address, amount])
    # Fill in details.
    # Block number will be filled in later, when confirmation updater picks a transaction receipt for this operation.
    op.txid = txid_to_bin(txid)
    op.block = None

    op.mark_performed()
    op.mark_complete()  # This cannot be cancelled


def withdraw(web3: Web3, dbsession: Session, op: CryptoAddressWithdraw):
    """Backend has different contract types for different assets."""
    eth = get_ether_asset(dbsession)

    if op.holding_account.asset == eth:
        return withdraw_eth(web3, dbsession, op)
    elif op.holding_account.asset.asset_class == AssetClass.token:
        return withdraw_token(web3, dbsession, op)
    else:
        raise RuntimeError("Unknown asset {}".format(op.holding_account.asset))


def create_token(web3: Web3, dbsession: Session, op: CryptoTokenCreation):
    """Creates a new token and assigns it ownership to user.

    """

    # Check everyting looks sane
    assert op.crypto_account.id
    assert op.crypto_account.account.id

    asset = op.holding_account.asset
    assert asset.id

    # Set information on asset that we have now created and have its smart contract id
    assert not asset.external_id, "Asset has been already assigned its smart contract id. Recreate error?"

    address = bin_to_eth_address(op.crypto_account.address.address)

    # Create Tonex proxy object
    token = Token.create_token(web3, name=asset.name, symbol=asset.symbol, supply=asset.supply, owner=address)

    # Call geth RPC API over Populus contract proxy
    op.txid = txid_to_bin(token.initial_txid)
    op.block = None
    op.external_address = eth_address_to_bin(token.address)

    asset.external_id = op.external_address

    op.mark_performed()


def import_token(web3: Web3, dbsession: Session,op: CryptoTokenCreation):
    """Import existing token smart contract as asset."""
    address = bin_to_eth_address(op.external_address)
    token = Token.get(web3, address)

    network = op.network

    def gen_error(e: Exception):
        # Set operation as impossible to complete
        # Set user readable and technical error explanation
        op.mark_failed()
        op.other_data["error"] = "Address did not provide EIP-20 token API:" + address
        op.other_data["exception"] = str(e)
        logger.exception(e)

    try:
        name = token.contract.call().name().decode("utf-8")
        symbol = token.contract.call().symbol().decode("utf-8")
        supply = Decimal(token.contract.call().totalSupply())
    except eth_abi.exceptions.DecodingError as e:
        # When we try to access a contract attrib which is not supported by underlying code
        gen_error(e)
        return

    asset = network.create_asset(name=name, symbol=symbol, supply=supply, asset_class=AssetClass.token)
    asset.external_id = op.external_address

    # Fill in balances for the addresses we host
    # TODO: Too much for one transaction
    for caddress in dbsession.query(CryptoAddress).all():

        # Returns 0 for unknown addresses
        try:
            amount = token.contract.call().balanceOf(bin_to_eth_address(caddress.address))
        except eth_abi.exceptions.DecodingError as e:
            # Bad contract doesn't define balanceOf()
            # This leaves badly imported asset
            gen_error(e)
            return

        if amount > 0:
            account = caddress.get_or_create_account(asset)
            account.account.do_withdraw_or_deposit(Decimal(amount), "Token contract import")

    op.mark_performed()
    op.mark_complete()


def register_eth_operations(registry: Registry):
    """Register handlers for different crypto operations.

    This maps database rows to functions they should perform in Ethereum service daemon.
    """

    registry.registerAdapter(factory=lambda op: create_address, required=(CryptoAddressCreation,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: withdraw, required=(CryptoAddressWithdraw,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: deposit_eth, required=(CryptoAddressDeposit,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: create_token, required=(CryptoTokenCreation,), provided=IOperationPerformer)
    registry.registerAdapter(factory=lambda op: import_token, required=(CryptoTokenImport,), provided=IOperationPerformer)


