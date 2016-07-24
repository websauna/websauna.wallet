"""Test hosted wallet ETH send and receive integrates with our wallet models."""
import time

import pytest
import transaction
from decimal import Decimal

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.models import AssetNetwork
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid, to_wei
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState
from websauna.wallet.models.blockchain import MultipleAssetAccountsPerAddress, CryptoAddressDeposit

# How many ETH we move for test transactiosn
from websauna.wallet.tests.eth.utils import wait_tx

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


