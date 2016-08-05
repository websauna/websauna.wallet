"""Confirmation routines to make sure our data gets to blockchain."""
from uuid import UUID

import time
import transaction

from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.models import CryptoOperation


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