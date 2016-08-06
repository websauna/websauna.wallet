"""Test hosted wallet ETH send and receive integrates with our wallet models."""
import time
from uuid import UUID

import pytest
import transaction
from decimal import Decimal
from web3 import Web3

from sqlalchemy.orm import Session

from populus.utils.transactions import wait_for_block_number
from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid, to_wei, wei_to_eth, bin_to_eth_address
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw
from websauna.wallet.models.account import AssetClass
from websauna.wallet.models.blockchain import CryptoAddressDeposit, import_token

# How many ETH we move for test transactiosn
from websauna.wallet.tests.eth.utils import wait_tx, get_withdrawal_fee, wait_for_op_confirmations, send_balance_to_address


TEST_VALUE = Decimal("0.01")


def test_create_eth_account(dbsession, eth_service, eth_network_id):
    """Create Ethereum user deposit address by deploying a hosted wallet contract through geth."""

    # Create CryptoAddressCreation operation
    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)

        address = CryptoAddress(network=network)

        dbsession.flush()

        # Generate address on the account
        op = CryptoAddressCreation(address)
        dbsession.add(op)
        dbsession.flush()

        op_id = op.id

    # Event cycle should perform the operation
    success_op_count, failed_op_count = eth_service.run_event_cycle()
    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        assert dbsession.query(CryptoOperation).count() == 1
        op = dbsession.query(CryptoOperation).get(op_id)
        assert op.completed_at
        assert op.block
        assert op.performed_at
        assert op.completed_at

        address = dbsession.query(CryptoAddress).first()
        assert address.address


def test_deposit_eth(dbsession, eth_network_id, web3, eth_service, coinbase, deposit_address):
    """Accept incoming deposit."""

    # Do a transaction over ETH network

    txid = send_balance_to_address(web3, deposit_address, TEST_VALUE)
    confirm_transaction(web3, txid)

    success_op_count, failed_op_count = eth_service.run_listener_operations()
    assert success_op_count == 1
    assert failed_op_count == 0

    # We get a operation, which is not resolved yet due to block confirmation numbers
    with transaction.manager:

        # Account not yet updated
        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        eth_asset = get_ether_asset(dbsession)
        assert address.get_account(eth_asset).account.get_balance() == 0

        # We have one ETH account on this address
        assert address.crypto_address_accounts.count() == 1

        # We have one pending operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 2  # Create + deposit
        op = ops[-1]
        assert isinstance(op, CryptoAddressDeposit)
        assert op.holding_account.get_balance() == TEST_VALUE
        assert op.completed_at is None
        opid = op.id

    # Wait that we reach critical confirmation count
    wait_for_op_confirmations(eth_service, opid)

    # Now account shoult have been settled
    with transaction.manager:

        # We have one complete operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 2  # Create + deposit
        op = ops[-1]
        assert isinstance(op, CryptoAddressDeposit)
        assert op.holding_account.get_balance() == 0
        assert op.completed_at is not None

        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()

        # We have one ETH account on this address
        assert address.crypto_address_accounts.count() == 1

        # We have one credited account
        eth_asset = get_ether_asset(dbsession)
        caccount = address.get_account(eth_asset)
        assert caccount.account.get_balance() == TEST_VALUE


def test_double_scan_deposit(dbsession, eth_network_id, web3, eth_service, coinbase, deposit_address):
    """Make sure that scanning the same transaction twice doesn't get duplicated in the database."""

    # Do a transaction over ETH network
    txid = send_balance_to_address(web3, deposit_address, TEST_VALUE)
    confirm_transaction(web3, txid)

    success_op_count, failed_op_count = eth_service.run_listener_operations()
    assert success_op_count == 1

    # Now force run over the same blocks again
    success_op_count, failed_op_count = eth_service.eth_wallet_listener.force_scan(0, web3.eth.blockNumber)
    assert success_op_count == 0
    assert failed_op_count == 0

    # We get a operation, which is not resolved yet due to block confirmation numbers
    with transaction.manager:
        # We have one pending operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 2  # Create + deposit


def test_withdraw_eth(dbsession: Session, eth_network_id: UUID, web3: Web3, eth_service: EthereumService, withdraw_address: str, target_account: str):
    """Perform a withdraw operation.

    Create a database address with balance.
    """

    # First check what's our balance before sending coins back
    current_balance = wei_to_eth(web3.eth.getBalance(target_account))
    assert current_balance == 0

    with transaction.manager:

        # Create withdraw operation
        caccount = dbsession.query(CryptoAddressAccount).one()

        #: We are going to withdraw the full amount on the account
        assert caccount.account.get_balance() == TEST_VALUE

        # Use 4 as the heurestics for block account that doesn't happen right away, but still sensible to wait for it soonish
        op = caccount.withdraw(TEST_VALUE, eth_address_to_bin(target_account), "Getting all the moneys", required_confirmation_count=4)

    success_op_count, failed_op_count = eth_service.run_waiting_operations()
    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        # We should have now three ops
        # One for creating the address
        # One for depositing value for the test
        # One for withdraw

        # We have one complete operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 3  # Create + deposit + withdraw
        op = ops[-1]
        assert isinstance(op, CryptoAddressWithdraw)
        assert op.broadcasted_at is not None  # This completes instantly, cannot be cancelled
        assert op.completed_at is None  # We need at least one confirmation
        assert op.block is None
        assert op.txid is not None
        txid = bin_to_txid(op.txid)

    # This should make the tx to included in a block
    confirm_transaction(web3, txid)

    # Now we should get block number for the withdraw
    eth_service.run_confirmation_updates()

    # Geth reflects the deposit instantly internally, doesn't wait for blocks
    fee = get_withdrawal_fee(web3)
    new_balance = wei_to_eth(web3.eth.getBalance(target_account))
    assert new_balance == current_balance + TEST_VALUE - fee

    current_block = web3.eth.blockNumber
    with transaction.manager:
        # Check we get block and txid

        # We have one complete operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 3  # Create + deposit + withdraw
        op = ops[-1]
        assert op.broadcasted_at is not None  # This completes instantly, cannot be cancelled
        assert op.completed_at is None, "Got confirmation for block {}, current {}, requires {}".format(op.block, current_block, op.required_confirmation_count)
        assert op.block is not None
        assert op.txid is not None
        block_num = op.block
        required_conf = op.required_confirmation_count

    # Wait block to make the confirmation happen
    wait_for_block_number(web3, block_num + required_conf + 1, timeout=60)

    # Now we should have enough blocks to mark the transaction as confirmed
    eth_service.run_confirmation_updates()

    with transaction.manager:
        # Check we get block and txid

        # We have one complete operation
        ops = list(dbsession.query(CryptoOperation).all())
        op = ops[-1]
        assert op.completed_at is not None


def test_create_token(dbsession, eth_network_id, eth_service, coinbase, deposit_address):
    """Test user initiated token creation."""

    # Initiate token creation operation
    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = network.create_asset(name="MyToken", symbol="MY", supply=Decimal(10000), asset_class=AssetClass.token)
        address = CryptoAddress.get_network_address(network, eth_address_to_bin(deposit_address))
        op = address.create_token(asset)
        opid = op.id
        aid = asset.id
        assert op.completed_at is None

        # Check asset is intact
        assert asset.symbol == "MY"
        assert asset.supply == 10000
        assert asset.name == "MyToken"

    # This gives op a txid when smart contract creation tx is posted to geth
    success_count, failure_count = eth_service.run_waiting_operations()
    assert success_count == 1
    assert failure_count == 0

    # Check that initial asset data is in place
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        address = CryptoAddress.get_network_address(network, eth_address_to_bin(deposit_address))
        asset = network.get_asset(aid)

        assert op.txid
        assert not op.block
        assert op.broadcasted_at is not None
        assert op.completed_at is None

        # Initial balance doesn't hit us until tx has been confirmed
        assert address.get_account(asset).account.get_balance() == 0

        # Asset has received its smart contract address
        assert asset.external_id

    # Wait that the smart contract creation is confirmed
    wait_for_op_confirmations(eth_service, opid)

    # Initial balance doesn't hit us until op has enough confirmations
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        address = CryptoAddress.get_network_address(network, eth_address_to_bin(deposit_address))
        asset = network.get_asset(aid)

        assert op.broadcasted_at is not None
        assert op.completed_at is not None
        assert address.get_account(asset).account.get_balance() == 10000


def test_import_token(dbsession, eth_network_id, web3: Web3, eth_service: EthereumService, coinbase: str, deposit_address: str, token: Token):
    """Import an existing smart contract token to system."""

    # Make sure we have an address that holds some of the tokens so it is cleared up during import
    txid = token.transfer(deposit_address, Decimal(4000))
    confirm_transaction(web3, txid)

    with transaction.manager:

        network = dbsession.query(AssetNetwork).get(eth_network_id)
        op = import_token(network, eth_address_to_bin(token.address))
        opid = op.id

        # Let's create another address that doesn't hold tokens
        # and see that import doesn't fail for it
        addr = CryptoAddress(network=network, address=eth_address_to_bin("0x2f70d3d26829e412a602e83fe8eebf80255aeea5"))
        dbsession.add(addr)

    success_count, failure_count = eth_service.run_waiting_operations()
    assert success_count == 1
    assert failure_count == 0

    # Check that we created a new asset and its imports where fulfilled
    with transaction.manager:

        op = dbsession.query(CryptoOperation).get(opid)
        assert op.completed_at

        # We got account with tokens on it
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        caddress = CryptoAddress.get_network_address(network, eth_address_to_bin(deposit_address))

        asset = network.assets.filter_by(external_id=eth_address_to_bin(token.address)).one()
        assert asset.name == "Mootoken"
        assert asset.symbol == "MOO"
        assert asset.supply == 10000

        caccount = caddress.get_account_by_address(eth_address_to_bin(token.address))
        assert caccount.account.get_balance() == 4000


def test_import_no_address_token(dbsession: Session, eth_network_id, web3: Web3, eth_service: EthereumService):
    """Import should fail for address that doesn't exist."""

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        # A random address
        op = import_token(network, eth_address_to_bin("0x2f70d3d26829e412a602e83fe8eebf80255aeea5"))
        opid = op.id

    # Success count here means the operation passed, but might be marked as failure
    success_count, failure_count = eth_service.run_waiting_operations()
    assert success_count == 1
    assert failure_count == 0

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.failed_at
        assert op.other_data["error"].startswith("Address did not provide EIP-20 token API:")


def test_deposit_token(dbsession, eth_network_id, web3: Web3, eth_service: EthereumService, coinbase: str, deposit_address: str, token: Token):
    """"See that we can deposit tokens to accounts."""

    # Import a contract where coinbase has all balance
    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        import_token(network, eth_address_to_bin(token.address))

    # Run import token operation
    success_count, failure_count = eth_service.run_waiting_operations()
    assert success_count == 1
    assert failure_count == 0

    # Coinbase transfers token balance to deposit address
    txid = token.transfer(deposit_address, Decimal(4000))
    confirm_transaction(web3, txid)

    # We should pick up incoming deposit
    success_count, failure_count = eth_service.run_listener_operations()
    assert success_count == 1
    assert failure_count == 0

    # Check that data is setup correctly on incoming transaction
    with transaction.manager:
        op = dbsession.query(CryptoOperation).all()[-1]
        opid = op.id
        assert not op.completed_at
        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        asset = op.holding_account.asset
        assert op.holding_account.get_balance() == 4000
        assert op.completed_at is None
        assert address.get_account(asset).account.get_balance() == 0  # Not credited until confirmations reached
        assert address.crypto_address_accounts.count() == 1

    # Wait the token transaction to get enough confirmations
    wait_for_op_confirmations(eth_service, opid)

    # Check that the transaction is not final
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.completed_at
        assert op.completed_at
        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        asset = op.holding_account.asset
        assert op.holding_account.get_balance() == 0
        assert address.get_account(asset).account.get_balance() == 4000


def test_withdraw_token(dbsession, eth_network_id, web3: Web3, eth_service: EthereumService, deposit_address: str, token_asset: str, target_account: str):
    """"See that we can withdraw token outside to an account."""

    with transaction.manager:
        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        asset = dbsession.query(Asset).get(token_asset)
        caccount = address.get_account(asset)

        op = caccount.withdraw(Decimal(2000), eth_address_to_bin(target_account), "Sending to friend")
        opid = op.id

        assert caccount.account.get_balance() == 8000

    # Run import token operation
    success_count, failure_count = eth_service.run_waiting_operations()
    assert success_count == 1
    assert failure_count == 0

    # TX was broadcasted, marked as complete
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert isinstance(op, CryptoAddressWithdraw)
        asset = dbsession.query(Asset).get(token_asset)
        assert op.broadcasted_at
        assert not op.completed_at

    wait_for_op_confirmations(eth_service, opid)

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.broadcasted_at
        assert op.completed_at
        asset = dbsession.query(Asset).get(token_asset)

        # Tokens have been removed on from account
        token = Token.get(web3, bin_to_eth_address(asset.external_id))
        assert token.contract.call().balanceOf(deposit_address) == 8000

        # Tokens have been credited on to account
        token = Token.get(web3, bin_to_eth_address(asset.external_id))
        assert token.contract.call().balanceOf(target_account) == 2000


def test_transfer_tokens_between_accounts(dbsession, eth_network_id, web3: Web3, eth_service: EthereumService, deposit_address: str, token_asset: str, coinbase: str):
    """Transfer tokens between two internal accounts.

    Do transfers in two batches to make sure subsequent events top up correctly.
    """

    # Initiate a target address creatin
    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        opid = CryptoAddress.create_address(network).id

    # Run address creation
    success_count, failure_count = eth_service.run_waiting_operations()
    assert success_count == 1
    assert failure_count == 0

    # We resolved address creation operation.
    # Get the fresh address for the future withdraw targets.
    with transaction.manager:
        op = dbsession.query(CryptoAddressCreation).get(opid)
        addr = op.address.address
        assert addr

    # Move tokens between accounts
    with transaction.manager:
        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        asset = dbsession.query(Asset).get(token_asset)
        caccount = address.get_account(asset)

        op = caccount.withdraw(Decimal(2000), addr, "Sending to friend")
        opid = op.id

    # Resolve the 1st transaction
    eth_service.run_event_cycle()
    wait_for_op_confirmations(eth_service, opid)

    # See that our internal balances match
    with transaction.manager:

        # Withdraw operation is complete
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.completed_at
        assert op.completed_at, "Op not confirmed {}".format(op)

        # We should have received a Transfer operation targetting target account
        op = dbsession.query(CryptoOperation).join(CryptoAddressAccount).join(CryptoAddress).filter_by(address=addr).one()
        opid = op.id
        confirmed = op.completed_at

    # Confirm incoming Transfer
    if not confirmed:
        wait_for_op_confirmations(eth_service, opid)

    # Check Transfer looks valid
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.completed_at
        assert op.completed_at, "Op not confirmed {}".format(op)

        asset = dbsession.query(Asset).get(token_asset)
        source = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        target = dbsession.query(CryptoAddress).filter_by(address=addr).one()

        assert source.get_account(asset).account.get_balance() == 8000
        assert target.get_account(asset).account.get_balance() == 2000

    # Add some ETH on deposit_address
    txid = send_balance_to_address(web3, deposit_address, TEST_VALUE)
    confirm_transaction(web3, txid)
    eth_service.run_event_cycle()

    # Wait for confirmations to have ETH deposit credired
    with transaction.manager:
        op = dbsession.query(CryptoOperation).filter_by(txid=txid_to_bin(txid)).one()
        opid = op.id
        confirmed = op.completed_at
    if not confirmed:
        wait_for_op_confirmations(eth_service, opid)

    # Send some more tokens + ether, so we see account can't get mixed up
    with transaction.manager:
        address = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        asset = dbsession.query(Asset).get(token_asset)
        caccount = address.get_account(asset)

        op = caccount.withdraw(Decimal(4000), addr, "Sending tokens to friend äää")

        eth_asset = get_ether_asset(dbsession)
        caccount = address.get_account(eth_asset)
        op = caccount.withdraw(TEST_VALUE, addr, "Sending ETH to friend äää")
        opid = op.id

    # Resolve second transaction
    eth_service.run_event_cycle()
    wait_for_op_confirmations(eth_service, opid)

    # See that our internal balances match
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.completed_at
        assert op.completed_at
        asset = dbsession.query(Asset).get(token_asset)
        source = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        target = dbsession.query(CryptoAddress).filter_by(address=addr).one()
        eth_asset = get_ether_asset(dbsession)

        assert source.get_account(asset).account.get_balance() == 4000
        assert target.get_account(asset).account.get_balance() == 6000
        assert target.get_account(eth_asset).account.get_balance() == TEST_VALUE

    # Transfer 3:
    # Send everything back plus some ether
    with transaction.manager:
        address = dbsession.query(CryptoAddress).filter_by(address=addr).one()
        asset = dbsession.query(Asset).get(token_asset)
        caccount = address.get_account(asset)

        op = caccount.withdraw(Decimal(6000), eth_address_to_bin(deposit_address), "Sending everything back to friend äää")
        opid = op.id

    # Resolve third transaction
    wait_for_op_confirmations(eth_service, opid)
    eth_service.run_event_cycle()

    # See that our internal balances match
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.completed_at
        assert op.completed_at
        asset = dbsession.query(Asset).get(token_asset)
        source = dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(deposit_address)).one()
        target = dbsession.query(CryptoAddress).filter_by(address=addr).one()

        assert source.get_account(asset).account.get_balance() == 10000
        assert target.get_account(asset).account.get_balance() == 0

        eth_asset = get_ether_asset(dbsession)
        assert source.get_account(eth_asset).account.get_balance() == 0
        assert target.get_account(eth_asset).account.get_balance() == TEST_VALUE
