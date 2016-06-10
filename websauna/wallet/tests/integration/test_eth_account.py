"""Test Ethereum account operations."""
import transaction
import mock

from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, Account, CryptoOperation, CryptoAddress


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
        op.address.address = "xxx"

    with mock.patch("websauna.wallet.ethereum.ops.create_address", new=_create_address):
        success_op_count, failed_op_count = eth_service.run_waiting_operations()

    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(op_id)
        assert op.completed_at

        address = dbsession.query(CryptoAddress).first()
        assert address.address



