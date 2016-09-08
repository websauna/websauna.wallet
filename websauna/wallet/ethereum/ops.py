"""Interaction between geth and database."""
from decimal import Decimal
import logging
from uuid import UUID

import eth_abi
from pyramid.registry import Registry
from sqlalchemy.orm import Session

from web3 import Web3
from websauna.system.model.retry import retryable

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.utils import txid_to_bin, eth_address_to_bin, bin_to_eth_address, to_wei
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import AssetClass, CryptoAddress, CryptoOperation
from websauna.wallet.models.blockchain import CryptoOperationType


logger = logging.getLogger(__name__)


def create_address(web3: Web3, dbsession: Session, opid: UUID):
    """User requests new hosted address.

    We create a hosted wallet contract. The contract id is associated with the user in the database. We hold the the only owner address of the wallet.

    The wallet code is based on https://github.com/ethereum/meteor-dapp-wallet/blob/master/Wallet.sol
    """

    assert isinstance(opid, UUID)

    @retryable(tm=dbsession.transaction_manager)
    def finish_op():
        op = dbsession.query(CryptoOperation).get(opid)
        txid = wallet.initial_txid
        receipt = web3.eth.getTransactionReceipt(txid)

        op.txid = txid_to_bin(txid)
        op.block = receipt["blockNumber"]
        op.address.address = eth_address_to_bin(wallet.address)
        op.external_address = op.address.address

        # There is no broadcast wait, so we can close this right away
        op.mark_performed()
        op.mark_broadcasted()
        op.mark_complete()

    logger.info("Starting wallet creation for %s", opid)
    wallet = HostedWallet.create(web3)
    logger.info("Updating db for wallet creation for %s", opid)
    finish_op()


def deposit_eth(web3: Web3, dbsession: Session, opid: UUID):
    """This can be settled internally, as we do not have any external communications in this point."""

    @retryable(tm=dbsession.transaction_manager)
    def perform_tx():
        op = dbsession.query(CryptoOperation).get(opid)
        op.mark_performed()
        op.mark_broadcasted()
        # Transaction confirmation count updater will make sure we have enough blocks,
        # and then will call mark_completed()

    perform_tx()


def withdraw_eth(web3: Web3, dbsession: Session, opid: UUID):
    """Perform ETH withdraw operation from the wallet."""

    @retryable(tm=dbsession.transaction_manager)
    def prepare_withdraw():
        # Check everyting looks sane
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.crypto_account.id
        assert op.crypto_account.account.id
        assert op.holding_account.id
        assert op.holding_account.get_balance() > 0
        assert op.external_address
        assert op.required_confirmation_count  # Should be set by the creator

        address = bin_to_eth_address(op.crypto_account.address.address)

        # How much we are withdrawing
        amount = op.holding_account.transactions.one().amount
        op.mark_performed()  # Don't pick this to action list anymore

        return address, amount, op.external_address

    @retryable(tm=dbsession.transaction_manager)
    def close_withdraw():
        # Fill in details.
        # Block number will be filled in later, when confirmation updater picks a transaction receipt for this operation.
        op = dbsession.query(CryptoOperation).get(opid)
        op.txid = txid_to_bin(txid)
        op.block = None
        op.mark_broadcasted()

    address, amount, external_address = prepare_withdraw()
    # Do actual network communications outside the transaction,
    # so we avoid double withdraws in the case transaction is retried
    wallet = HostedWallet.get(web3, address)
    txid = wallet.withdraw(bin_to_eth_address(external_address), amount)
    close_withdraw()


def withdraw_token(web3: Web3, dbsession: Session, opid: UUID):
    """Perform token withdraw operation from the wallet."""

    @retryable(tm=dbsession.transaction_manager)
    def prepare_withdraw():
        # Check everyting looks sane
        op = dbsession.query(CryptoOperation).get(opid)
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
        op.mark_performed()  # Don't try to pick this op automatically again
        return from_address, to_address, asset_address, amount

    @retryable(tm=dbsession.transaction_manager)
    def close_withdraw():
        # Fill in details.
        # Block number will be filled in later, when confirmation updater picks a transaction receipt for this operation.
        op = dbsession.query(CryptoOperation).get(opid)
        op.txid = txid_to_bin(txid)
        op.block = None
        op.mark_broadcasted()

    from_address, to_address, asset_address, amount = prepare_withdraw()
    wallet = HostedWallet.get(web3, from_address)
    token = Token.get(web3, asset_address)
    amount = token.validate_transfer_amount(amount)
    # Perform actual transfer outside retryable transaction
    # boundaries to avoid double withdrwa
    txid = wallet.execute(token.contract, "transfer", [to_address, amount])
    close_withdraw()



def withdraw(web3: Web3, dbsession: Session, opid: UUID):
    """Backend has different contract types for different assets."""

    @retryable(tm=dbsession.transaction_manager)
    def resolve_asset():
        op = dbsession.query(CryptoOperation).get(opid)
        eth = get_ether_asset(dbsession, network=op.network)

        if op.holding_account.asset == eth:
            return "eth"
        elif op.holding_account.asset.asset_class == AssetClass.token:
            return "token"
        else:
            raise RuntimeError("Unknown asset {}".format(op.holding_account.asset))

    asset_type = resolve_asset()

    if asset_type == "token":
        return withdraw_token(web3, dbsession, opid)
    else:
        return withdraw_eth(web3, dbsession, opid)


def create_token(web3: Web3, dbsession: Session, opid: UUID):
    """Creates a new token and assigns it ownership to user.

    """

    # TODO: Factor our blockchain calls outside tx
    @retryable(tm=dbsession.transaction_manager)
    def perform_tx():
        op = dbsession.query(CryptoOperation).get(opid)
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
        op.mark_broadcasted()
        # This will be marked complete after we get transaction confirmation count from the network

    perform_tx()

def import_token(web3: Web3, dbsession: Session, opid: UUID):
    """Import existing token smart contract as asset."""

    # TODO: split to smaller transactions
    @retryable(tm=dbsession.transaction_manager)
    def perform_tx():
        op = dbsession.query(CryptoOperation).get(opid)
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
            name = token.contract.call().name()
            symbol = token.contract.call().symbol()
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

        # This operation immediately closes
        op.mark_performed()
        op.mark_broadcasted()
        op.mark_complete()

    perform_tx()


def get_eth_operations(registry: Registry):
    """Register handlers for different crypto operations.

    This maps database rows to functions they should perform in Ethereum service daemon.
    """

    op_map = {
        CryptoOperationType.withdraw: withdraw,
        CryptoOperationType.deposit: deposit_eth,
        CryptoOperationType.import_token: import_token,
        CryptoOperationType.create_token: create_token,
        CryptoOperationType.create_address: create_address,
    }
    return op_map


