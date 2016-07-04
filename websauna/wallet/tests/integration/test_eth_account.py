"""Test Ethereum account operations."""
import transaction
import mock
from decimal import Decimal

from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw

TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"


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


def test_deposit_eth_account(dbsession, eth_network_id, eth_service, eth_faux_address):
    """Deposit Ethereums to an account."""


def test_withdraw_eth_account(dbsession, eth_service, eth_network_id, eth_asset_id):
    """Withdraw from Ethereums to to an address."""

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
        pass

    with mock.patch("websauna.wallet.ethereum.ops.withdraw_eth", new=_withdraw_eth):
        success_op_count, failed_op_count = eth_service.run_waiting_operations()



def test_create_token_account():
    pass

def test_deposit_token_account():
    pass

def test_withdraw_token_account():
    pass

