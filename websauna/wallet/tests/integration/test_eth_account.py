"""Test Ethereum account operations."""
import transaction
import mock
from decimal import Decimal

from websauna.wallet.ethereum.utils import eth_address_to_bin
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset

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

    with transaction.manager:
        assert ca_account.account.get_balance() == Decimal(0)


