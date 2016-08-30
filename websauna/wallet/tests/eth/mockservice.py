"""Mock out Ethereum backend for testing."""
from uuid import UUID

from sqlalchemy.orm import Session

import transaction
from pyramid.registry import Registry
from websauna.wallet.ethereum.dboperationqueue import OperationQueueManager
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import eth_address_to_bin, bin_to_eth_address, txid_to_bin
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoOperationType


TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"
TEST_ADDRESSES = []
TEST_ADDRESS_INITIAL_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"

TEST_TOKEN_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"
TEST_TOKEN_ADDRESS = "0x5589C14FbC92A73809fBCfF33Ab40eFc7E8E8467 "


def _create_address(service, dbsession, opid):

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        txid = TEST_ADDRESS_INITIAL_TXID

        op.txid = txid_to_bin(txid)
        op.block = 666
        op.address.address = eth_address_to_bin(TEST_ADDRESS)
        op.external_address = op.address.address

        op.mark_performed()
        op.mark_broadcasted()
        op.mark_complete()


def _create_token(service, dbsession, opid):
    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        # Check everyting looks sane
        assert op.crypto_account.id
        assert op.crypto_account.account.id

        asset = op.holding_account.asset
        assert asset.id

        # Set information on asset that we have now created and have its smart contract id
        assert not asset.external_id, "Asset has been already assigned its smart contract id. Recreate error?"

        address = bin_to_eth_address(op.crypto_account.address.address)

        # Call geth RPC API over Populus contract proxy
        op.txid = txid_to_bin(TEST_TOKEN_TXID)
        op.block = None
        op.external_address = eth_address_to_bin(TEST_ADDRESS)

        asset.external_id = op.external_address

        op.mark_performed()
        op.mark_broadcasted()
        op.mark_complete()


class DummyOperationQueueManager(OperationQueueManager):

    def get_eth_operations(self, registry):
        """Mock out all operations."""

        op_map = {
            #CryptoOperationType.withdraw: withdraw,
            # CryptoOperationType.deposit: deposit_eth,
            #CryptoOperationType.import_token: import_token,
            CryptoOperationType.create_token: _create_token,
            CryptoOperationType.create_address: _create_address,
        }
        return op_map


class MockEthereumService(EthereumService):
    """Mock actual Ethereum backend away.

    * No network communications

    * All operations will always success instantly

    * Deposits and withdraws come and go to /dev/null
    """

    def __init__(self, asset_network_id: UUID, dbsession: Session, registry: Registry):
        self.web3 = None
        self.asset_network_id = asset_network_id
        self.dbsession = dbsession
        self.registry = registry

        self.setup_listeners()

    def run_listener_operations(self):
        """We don't listen to network."""
        total_success = total_failure = 0
        return total_success, total_failure

    def run_confirmation_updates(self):
        """We don't receive network confirmations."""
        return self.confirmation_updater.poll()

    def run_waiting_operations(self):
        """Run all operations that are waiting to be executed.

        :return: Number of operations (performed successfully, failed)
        """
        return self.op_queue_manager.run_waiting_operations()

    def setup_listeners(self):
        self.op_queue_manager = DummyOperationQueueManager(self.web3, self.dbsession, self.asset_network_id, self.registry)

