"""Test hosted wallet ETH send and receive integrates with our wallet models."""
import time
from uuid import UUID

import pytest
import transaction
from decimal import Decimal

from eth_ipc_client import Client
from sqlalchemy.orm import Session

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import AssetNetwork
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid, to_wei, wei_to_eth
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState
from websauna.wallet.models.blockchain import MultipleAssetAccountsPerAddress, CryptoAddressDeposit

# How many ETH we move for test transactiosn
from websauna.wallet.tests.eth.utils import wait_tx, get_withdrawal_fee

TEST_VALUE = Decimal("0.01")


def test_create_eth_account(dbsession, eth_service, eth_network_id, client):
    """Create Ethereum account on Ethereum node."""

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)

        address = CryptoAddress(network=network)

        dbsession.flush()

        # Generate address on the account
        op = CryptoAddressCreation(address)
        dbsession.add(op)
        dbsession.flush()

        op_id = op.id

    success_op_count, failed_op_count = eth_service.run_waiting_operations()

    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(op_id)
        assert op.completed_at
        assert op.block

        address = dbsession.query(CryptoAddress).first()
        assert address.address


def test_deposit_eth(dbsession, eth_network_id, client, eth_service, coinbase, deposit_address):
    """Accept incoming deposit."""

    # Do a transaction over ETH network
    txid = client.send_transaction(_from=coinbase, to=deposit_address, value=to_wei(TEST_VALUE,))
    wait_tx(client, txid)

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

    # Wait until the transaction confirms (1 confirmations)
    deadline = time.time() + 47
    while time.time() < deadline:
        success_op_count, failed_op_count = eth_service.run_confirmation_updates()
        if success_op_count > 0:
            break
        if failed_op_count > 0:
            pytest.fail("hsit")
        time.sleep(1)

    if time.time() > deadline:
        pytest.fail("Did not receive confirmation updates")

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


def test_double_scan_deposit(dbsession, eth_network_id, client, eth_service, coinbase, deposit_address):
    """Make sure that scanning the same transaction twice doesn't get duplicated in the database."""

    # Do a transaction over ETH network
    txid = client.send_transaction(_from=coinbase, to=deposit_address, value=to_wei(TEST_VALUE, ))
    wait_tx(client, txid)

    success_op_count, failed_op_count = eth_service.run_listener_operations()
    assert success_op_count == 1

    # Now force run over the same blocks again
    success_op_count, failed_op_count = eth_service.eth_wallet_listener.force_scan(0, client.get_block_number())
    assert success_op_count == 0
    assert failed_op_count == 0

    # We get a operation, which is not resolved yet due to block confirmation numbers
    with transaction.manager:
        # We have one pending operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 2  # Create + deposit


def test_withdraw_eth(dbsession: Session, eth_network_id: UUID, client: Client, eth_service: EthereumService, withdraw_address: str, target_account: str):
    """Perform a withdraw operation.

    Create a database address with balance.
    """

    # First check what's our balance before sending coins back
    current_balance = wei_to_eth(client.get_balance(target_account))
    assert client.get_balance(withdraw_address) > 0

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
        assert op.completed_at is not None  # This completes instantly, cannot be cancelled
        assert op.confirmed_at is None  # We need at least one confirmation
        assert op.block is None
        assert op.txid is not None
        txid = bin_to_txid(op.txid)

    # This should make the tx to included in a block
    client.wait_for_transaction(txid)

    # Now we should get block number for the withdraw
    eth_service.run_confirmation_updates()

    # Geth reflects the deposit instantly internally, doesn't wait for blocks
    fee = get_withdrawal_fee(client)
    new_balance = wei_to_eth(client.get_balance(target_account))
    assert new_balance == current_balance + TEST_VALUE - fee

    current_block = client.get_block_number()
    with transaction.manager:
        # Check we get block and txid

        # We have one complete operation
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 3  # Create + deposit + withdraw
        op = ops[-1]
        assert op.completed_at is not None  # This completes instantly, cannot be cancelled
        assert op.confirmed_at is None, "Got confirmation for block {}, current {}, requires {}".format(op.block, current_block, op.required_confirmation_count)
        assert op.block is not None
        assert op.txid is not None
        block_num = op.block
        required_conf = op.required_confirmation_count

    # Wait block to make the confirmation happen
    client.wait_for_block(block_num + required_conf + 1)

    # Now we should have enough blocks to mark the transaction as confirmed
    eth_service.run_confirmation_updates()

    with transaction.manager:
        # Check we get block and txid

        # We have one complete operation
        ops = list(dbsession.query(CryptoOperation).all())
        op = ops[-1]
        assert op.confirmed_at is not None










