import threading
from typing import Iterable, List, Tuple
from uuid import UUID
import logging

import transaction
from pyramid.registry import Registry

from sqlalchemy.orm import Session
from websauna.utils.time import now
from websauna.wallet.ethereum.interfaces import IOperationPerformer
from websauna.wallet.models import CryptoOperation, CryptoOperationState
from .ethjsonrpc import EthJsonRpc


logger = logging.getLogger(__name__)


class EthereumService:
    """Ethereum service takes care of synchronizing operations between internal database and Ethereum daemon.

    We take a simple approach where we have one service / db running one single thread which does all operations serial manner.

    When testing, we call functions directly.
    """

    def __init__(self, client: EthJsonRpc, asset_network_id: UUID, dbsession: Session, registry: Registry):
        self.client = client
        self.asset_network_id = asset_network_id
        self.dbsession = dbsession
        self.registry = registry

    def get_waiting_operation_ids(self) -> List[UUID]:
        """Get list of operations we need to attempt to perform.

        Perform as one transaction.
        """

        with transaction.manager:
            wait_list = self.dbsession.query(CryptoOperation, CryptoOperation.id, CryptoOperation.state).filter_by(network_id=self.asset_network_id, state=CryptoOperationState.waiting)

            # Flatten
            wait_list = [o.id for o in wait_list]

        return wait_list

    def run_waiting_operations(self) -> Tuple[int, int]:
        """Run all operations that are waiting to be executed.

        :return: Number of operations (performed successfully, failed)
        """

        success_count = 0
        failure_count = 0

        ops = self.get_waiting_operation_ids()
        for o_id in ops:
            with transaction.manager:
                op = self.dbsession.query(CryptoOperation).get(o_id)
                op.attempted_at = now()
                op.attempts += 1
                logger.debug("Attempting to perform operation %s, attempt %d", op, op.attempts)

            with transaction.manager:
                try:
                    op = self.dbsession.query(CryptoOperation).get(o_id)

                    # Get a function to perform the op using adapters
                    performer = self.registry.queryAdapter(op, IOperationPerformer)
                    if not performer:
                        raise RuntimeError("Doesn't have a performer for operation {}".format(performer))

                    # Do the actual operation
                    performer(self, op)

                    op.state = CryptoOperationState.success
                    op.completed_at = now()

                    success_count += 1

                except Exception as e:
                    failure_count += 1
                    logger.error("Crypto operation failure %s", e)
                    logger.exception(e)
                    raise

        return success_count, failure_count

    def run_event_cycle(self):
        pass

