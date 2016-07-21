"""Test Ethereum model operations."""

import pytest
import transaction
import mock
from decimal import Decimal

import sqlalchemy
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState
from websauna.wallet.models.blockchain import MultipleAssetAccountsPerAddress

TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"

TEST_TXID = "0xdf829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"


def test_create_eth_account(dbsession, eth_network_id, eth_service):
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

    def _create_address(service, op):
        assert isinstance(op.address, CryptoAddress)
        op.address.address = eth_address_to_bin(TEST_ADDRESS)

    with mock.patch("websauna.wallet.ethereum.ops.create_address", new=_create_address):
        success_op_count, failed_op_count = eth_service.run_waiting_operations()

    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(op_id)
        assert op.completed_at

        address = dbsession.query(CryptoAddress).first()
        assert address.address


def test_double_address(dbsession, eth_network_id):
    """Cannot create Address object under the same network twice."""

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        with transaction.manager:
            network = dbsession.query(AssetNetwork).get(eth_network_id)
            address = CryptoAddress(network=network, address=eth_address_to_bin(TEST_ADDRESS))
            dbsession.add(address)
            dbsession.flush()
            address = CryptoAddress(network=network, address=eth_address_to_bin(TEST_ADDRESS))
            dbsession.add(address)


def test_create_address_accounts(dbsession, eth_network_id, eth_service, eth_faux_address, eth_asset_id):
    """Check that we can cerate different accounts under an account."""

    # Create ETH account
    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        address = CryptoAddress(network=network, address=eth_address_to_bin(TEST_ADDRESS))
        asset = dbsession.query(Asset).get(eth_asset_id)
        dbsession.flush()
        account = address.get_or_create_account(asset)
        account_id = account.id

    # We get it reflected back second time
    with transaction.manager:
        address = dbsession.query(CryptoAddress).one()
        asset = dbsession.query(Asset).get(eth_asset_id)
        account = address.get_or_create_account(asset)
        assert account.id == account_id

    # We cannot create double account for the same asset
    with pytest.raises(MultipleAssetAccountsPerAddress):
        with transaction.manager:
            address = dbsession.query(CryptoAddress).one()
            asset = dbsession.query(Asset).get(eth_asset_id)
            address.create_account(asset)


def test_deposit_eth_account(dbsession, eth_network_id, eth_service, eth_asset_id):
    """Deposit Ethereums to an account."""

    # Create ETH holding account under an address
    with transaction.manager:

        # First create the address which holds our account
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        address = CryptoAddress(network=network, address=eth_address_to_bin(TEST_ADDRESS))
        dbsession.add(address)
        dbsession.flush()

    # Create deposit op
    with transaction.manager:
        address = dbsession.query(CryptoAddress).one_or_none()
        asset = dbsession.query(Asset).get(eth_asset_id)
        txid = txid_to_bin(TEST_TXID)
        op = address.deposit(Decimal(10), asset, txid, bin_to_txid(txid))
        dbsession.add(op)

    # Resolve deposit op
    with transaction.manager:
        success_op_count, failed_op_count = eth_service.run_waiting_operations()
        assert success_op_count == 1
        assert failed_op_count == 0

    # Check balances are settled
    with transaction.manager:
        address = dbsession.query(CryptoAddress).one_or_none()
        asset = dbsession.query(Asset).get(eth_asset_id)
        account = address.get_account(asset)
        op = dbsession.query(CryptoOperation).one()
        assert account.account.get_balance() == Decimal(10)
        assert op.holding_account.get_balance() == 0

        # Transaction label should be the Ethereum txid
        tx = account.account.transactions.one()
        assert tx.message == TEST_TXID


def test_double_deposit_same_tx(dbsession, eth_network_id, eth_service, eth_asset_id):
    """Check that we have some logic to avoid depositing the same asset twice."""

    # Create ETH holding account under an address
    with transaction.manager:

        # First create the address which holds our account
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        address = CryptoAddress(network=network, address=eth_address_to_bin(TEST_ADDRESS))
        dbsession.add(address)
        dbsession.flush()

    # Create deposit op
    with transaction.manager:
        address = dbsession.query(CryptoAddress).one_or_none()
        asset = dbsession.query(Asset).get(eth_asset_id)
        txid = txid_to_bin(TEST_TXID)
        op = address.deposit(Decimal(10), asset, txid, bin_to_txid(txid))
        dbsession.add(op)
        dbsession.flush()
        op_id = op.id

    with transaction.manager:
        address = dbsession.query(CryptoAddress).one_or_none()
        asset = dbsession.query(Asset).get(eth_asset_id)
        txid = txid_to_bin(TEST_TXID)
        op = address.deposit(Decimal(10), asset, txid, bin_to_txid(txid))
        assert op.id == op_id
        assert dbsession.query(CryptoOperation).count() == 1


def test_withdraw_eth_account(dbsession, eth_service, eth_network_id, eth_asset_id):
    """Withdraw ETHs to an address."""

    # Create ETH holding account under an address
    with transaction.manager:

        # First create the address which holds our account
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        address = CryptoAddress(network=network, address=eth_address_to_bin(TEST_ADDRESS))
        dbsession.flush()

        assert address.id
        assert address.address
        asset = dbsession.query(Asset).get(eth_asset_id)

        # Create an account of ETH tokens on that address
        ca_account = address.create_account(asset)

    # It should have zero balance by default
    with transaction.manager:
        ca_account = dbsession.query(CryptoAddressAccount).one_or_none()
        assert ca_account.account.asset_id == eth_asset_id
        assert ca_account.account.get_balance() == Decimal(0)

    # Faux top up so we have value to withdraw
    with transaction.manager:
        ca_account = dbsession.query(CryptoAddressAccount).one_or_none()
        assert ca_account.account.do_withdraw_or_deposit(Decimal("+10"), "Faux top up")

    # Create withdraw operations
    withdraw_address = eth_address_to_bin(TEST_ADDRESS)
    with transaction.manager:
        ca_account = dbsession.query(CryptoAddressAccount).one_or_none()
        op = ca_account.withdraw(Decimal("10"), withdraw_address, "Bailing out")

        # We withdraw 10 ETHs
        assert op.holding_account.get_balance() == Decimal("10")
        assert op.holding_account.asset == dbsession.query(Asset).get(eth_asset_id)
        assert op.holding_account.transactions.count() == 1
        assert op.holding_account.transactions.first().message == "Bailing out"

        # Check all looks good on sending account
        assert ca_account.account.transactions.count() == 2
        assert ca_account.account.transactions.all()[0].message == "Faux top up"
        assert ca_account.account.transactions.all()[1].message == "Bailing out"
        assert ca_account.account.get_balance() == 0

    def _withdraw_eth(service, op):
        # Mocked withdraw op that always success
        op.txid = txid_to_bin(TEST_TXID)
        op.mark_complete()

    with mock.patch("websauna.wallet.ethereum.ops.withdraw_eth", new=_withdraw_eth):
        success_op_count, failed_op_count = eth_service.run_waiting_operations()

    # Check that operations have been marked as success
    with transaction.manager:
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 1
        assert isinstance(ops[0], CryptoAddressWithdraw)
        assert ops[0].state == CryptoOperationState.success
        assert ops[0].txid == txid_to_bin(TEST_TXID)

