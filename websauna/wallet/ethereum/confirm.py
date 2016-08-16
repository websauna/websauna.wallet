"""Confirmation routines to make sure our data gets to blockchain."""
from uuid import UUID
import logging
import time
import transaction

from websauna.system.model.retry import ensure_transactionless, retryable
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoOperationState
from websauna.wallet.models.heartbeat import is_network_alive


logger = logging.getLogger(__name__)


class OpConfirmationFailed(Exception):
    pass


def wait_for_op_confirmations(eth_service: EthereumService, opid: UUID, timeout=60):
    """Wait that an op reaches required level of confirmations."""

    with transaction.manager:
        op = eth_service.dbsession.query(CryptoOperation).get(opid)
        if op.completed_at:
            assert op.required_confirmation_count
            return

    # Wait until the transaction confirms (1 confirmations)
    deadline = time.time() + timeout
    while time.time() < deadline:
        success_op_count, failed_op_count = eth_service.run_event_cycle()
        if success_op_count > 0:

            # Check our op went through
            with transaction.manager:
                op = eth_service.dbsession.query(CryptoOperation).get(opid)
                if op.completed_at:
                    return

        if failed_op_count > 0:
            with transaction.manager:
                op = eth_service.dbsession.query(CryptoOperation).get(opid)
                raise OpConfirmationFailed("Failures within confirmation wait should not happen, op is {}".format(op))

        time.sleep(1)

        with transaction.manager:
            op = eth_service.dbsession.query(CryptoOperation).get(opid)
            logger.info("Waiting op to complete %s", op)

    if time.time() > deadline:
        with transaction.manager:
            op = eth_service.dbsession.query(CryptoOperation).get(opid)
            raise OpConfirmationFailed("Did not receive confirmation updates: {}".format(op))


def finalize_pending_crypto_ops(dbsession, timeout=90):
    """Wait all pending operations to complete.

    This assumes you have an Ethereum service running on a background.
    """

    ensure_transactionless()

    # Get list of ops we need to clear
    @retryable
    def fetch_ids():
        ops = dbsession.query(CryptoOperation).filter(CryptoOperation.state.in_([CryptoOperationState.waiting, CryptoOperationState.pending,]))
        ids = [op.id for op in ops]
        return ids

    @retryable
    def check_op_completion(id):
        op = dbsession.query(CryptoOperation).get(id)

        network = op.network
        if not is_network_alive(network):
            time.sleep(5) #  Give some extra time to recover
            if not is_network_alive(network):
                raise RuntimeError("Tried to complete against dead network: {}, op {}".format(network, op))

        # Cleared this item
        if op.completed_at:
            logger.info("Finished %s", op)
            return True

        if op.failed_at:
            raise RuntimeError("Op failed while waiting: {}".format(op))

        return False

    # Wait until all ops clear correctly
    deadline = time.time() + timeout

    ids = fetch_ids()

    logger.info("Waiting for %d operations to finish", len(ids))

    while time.time() < deadline:

        if not ids:
            # All ops cleared
            logger.info("All ops clear")
            return

        # Filter out completed operations
        ids = [id for id in ids if check_op_completion(id) == False]
        time.sleep(1)

    raise RuntimeError("Could not confirm all operations")

