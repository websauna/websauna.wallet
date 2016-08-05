"""Confirmation routines to make sure our data gets to blockchain."""
from uuid import UUID

import time
import transaction

from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoOperationState
from websauna.wallet.models.heartbeat import is_network_alive


class OpConfirmationFailed(Exception):
    pass


def wait_for_op_confirmations(eth_service: EthereumService, opid: UUID):
    """Wait that an op reaches required level of confirmations."""

    with transaction.manager:
        op = eth_service.dbsession.query(CryptoOperation).get(opid)
        if op.confirmed_at:
            assert op.required_confirmation_count
            return

    # Wait until the transaction confirms (1 confirmations)
    deadline = time.time() + 47
    while time.time() < deadline:
        success_op_count, failed_op_count = eth_service.run_event_cycle()
        if success_op_count > 0:

            # Check our op went through
            with transaction.manager:
                op = eth_service.dbsession.query(CryptoOperation).get(opid)
                if op.confirmed_at:
                    break

        if failed_op_count > 0:
            with transaction.manager:
                op = eth_service.dbsession.query(CryptoOperation).get(opid)
                raise OpConfirmationFailed("Failures within confirmation wait should not happen, op is {}".format(op))

        time.sleep(1)

    if time.time() > deadline:
        raise OpConfirmationFailed("Did not receive confirmation updates")


def finalize_pending_crypto_ops(dbsession, timeout=90):
    """Wait all pending operations to complete.

    This assumes you have an Ethereum service running on a background.
    """

    # Get list of ops we need to clear
    with transaction.manager:
        ops = dbsession.query(CryptoOperation).filter(CryptoOperation.state.in_(CryptoOperationState.waiting, CryptoOperationState.pending, ))
        ids = [op.id for op in ops]

    # Wait until all ops clear correctly
    deadline = time.time() + timeout

    while time.time() < deadline:

        if not ids:
            # All ops cleared
            return

        for id in ids:
            with transaction.manager:
                op = dbsession.query(CryptoOperation).get(id)

                network = op.network
                if not is_network_alive(network):
                    raise RuntimeError("Tried to complete against dead network: {}, op {}".format(network, op))

                #  Cleared this item
                if op.completed_at:
                    ids.remove(id)

                if op.failed_at:
                    raise RuntimeError("Op failed while waiting: {}".format(op))
        time.sleep(1)

    raise RuntimeError("Could not confirm all operations")

