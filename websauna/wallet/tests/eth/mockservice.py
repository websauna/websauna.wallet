"""Mock out Ethereum backend for testing."""
from uuid import UUID

from sqlalchemy.orm import Session

import transaction
from pyramid.registry import Registry
from websauna.wallet.ethereum.dbconfirmationupdater import DatabaseConfirmationUpdater
from websauna.wallet.ethereum.dboperationqueue import OperationQueueManager
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import eth_address_to_bin, bin_to_eth_address, txid_to_bin
from websauna.wallet.events import CryptoOperationCompleted, IncomingCryptoDeposit
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoOperationType
from websauna.wallet.models import CryptoOperationState
from websauna.wallet.models import CryptoAddressDeposit


TEST_ADDRESS_INITIAL_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"

TEST_TOKEN_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"
TEST_TOKEN_ADDRESS = "0x5589C14FbC92A73809fBCfF33Ab40eFc7E8E8467"


def _create_address(web3, dbsession, opid):

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        txid = TEST_ADDRESS_INITIAL_TXID

        # Deterministically pull faux addresses from pool
        network = op.network
        address_pool = network.other_data["test_address_pool"]
        address = address_pool.pop()

        op.txid = txid_to_bin(txid)
        op.block = 666
        op.address.address = eth_address_to_bin(address)
        op.external_address = op.address.address

        op.mark_performed()
        op.mark_broadcasted()


def _create_token(web3, dbsession, opid):
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
        op.external_address = eth_address_to_bin(TEST_TOKEN_ADDRESS)

        asset.external_id = op.external_address

        op.mark_performed()
        op.mark_broadcasted()


def _deposit_eth(web3, dbsession: Session, opid: UUID):
    """This can be settled internally, as we do not have any external communications in this point."""

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        op.mark_performed()
        op.mark_broadcasted()


def _withdraw(web3, dbsession: Session, opid: UUID):

    with transaction.manager:
        # Check everyting looks sane
        op = dbsession.query(CryptoOperation).get(opid)
        assert op.crypto_account.id
        assert op.crypto_account.account.id
        assert op.holding_account.id
        assert op.holding_account.get_balance() > 0
        assert op.external_address
        assert op.required_confirmation_count  # Should be set by the creator

        op.mark_performed()  # Don't try to pick this op automatically again

        # Fill in details.
        # Block number will be filled in later, when confirmation updater picks a transaction receipt for this operation.
        op = dbsession.query(CryptoOperation).get(opid)
        op.txid = txid_to_bin(TEST_ADDRESS_INITIAL_TXID)
        op.block = None
        op.mark_broadcasted()


class DummyOperationQueueManager(OperationQueueManager):

    def get_eth_operations(self, registry):
        """Mock out all operations."""

        op_map = {
            CryptoOperationType.withdraw: _withdraw,
            CryptoOperationType.deposit: _deposit_eth,
            #CryptoOperationType.import_token: import_token,
            CryptoOperationType.create_token: _create_token,
            CryptoOperationType.create_address: _create_address,
        }
        return op_map


class DummyDatabaseConfirmationUpdater(DatabaseConfirmationUpdater):
    """Confirm all operations in the queue."""

    def __init__(self, dbsession: Session, network_id, registry):
        self.network_id = network_id
        self.dbsession = dbsession
        self.registry = registry

    def poll(self):
        with transaction.manager:
            ops = self.dbsession.query(CryptoOperation).filter(CryptoOperation.state == CryptoOperationState.broadcasted, CryptoOperation.network_id == self.network_id)
            updates = 0
            for op in ops:

                # We don't have wallet updater, so we short cut deposit to user logic here
                if isinstance(op, CryptoAddressDeposit):
                    self.registry.notify(IncomingCryptoDeposit(op, self.registry, None))

                if op.update_confirmations(999):
                    self.registry.notify(CryptoOperationCompleted(op, self.registry, None))
                    updates += 1
            return updates, 0


class MockEthereumService(EthereumService):
    """Mock actual Ethereum backend away.

    * No network communications

    * All operations will always success instantly

    * All operations get confirmed instantly

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
        success = failure = 0
        s, f = self.op_queue_manager.run_waiting_operations()
        success += s
        failure += f

        s, f = self.confirmation_updater.poll()
        success += s
        failure += f

        return success, failure

    def setup_listeners(self):
        self.op_queue_manager = DummyOperationQueueManager(self.web3, self.dbsession, self.asset_network_id, self.registry)
        self.confirmation_updater = DummyDatabaseConfirmationUpdater(self.dbsession, self.asset_network_id, self.registry)

    def run_test_ops(self):
        """Finish all operations with a unit test."""
        success, failures = self.run_waiting_operations()
        assert success > 0
        assert failures == 0
