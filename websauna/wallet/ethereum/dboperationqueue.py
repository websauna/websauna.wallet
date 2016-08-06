import logging
import threading
from typing import List, Tuple
from uuid import UUID

import transaction
from pyramid import registry
from pyramid.registry import Registry
from sqlalchemy.orm import Session
from sqlalchemy.orm.instrumentation import instance_state
from web3 import Web3

from websauna.system.model.retry import retryable
from websauna.utils.time import now
from websauna.wallet.ethereum.interfaces import IOperationPerformer
from websauna.wallet.events import CryptoOperationComplete
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoOperationState
from websauna.wallet.models.blockchain import CryptoOperationType

logger = logging.getLogger(__name__)


class OperationQueueManager:
    """Run waiting operatins created in a web interface in a separate proces."""

    def __init__(self, web3: Web3, dbsession: Session, asset_network_id, registry: Registry):
        assert isinstance(registry, Registry)
        self.web3 = web3
        self.dbsession = dbsession
        self.asset_network_id = asset_network_id
        self.registry = registry

    @retryable
    def get_waiting_operation_ids(self) -> List[Tuple[UUID, CryptoOperationType]]:
        """Get list of operations we need to attempt to perform.

        Perform as one transaction.
        """

        wait_list = self.dbsession.query(CryptoOperation, CryptoOperation.id, CryptoOperation.state, CryptoOperation.operation_type).filter_by(network_id=self.asset_network_id, state=CryptoOperationState.waiting)

        # Flatten
        wait_list = [(o.id, o.operation_type) for o in wait_list]

        return wait_list

    @retryable
    def notify_op_complete(self, opid):
        # Post the event completion info
        op = self.dbsession.query(CryptoOperation).get(opid)
        self.registry.notify(CryptoOperationComplete(op, self.registry, self.web3))
        logger.info("Operationg success: %s", op)

    def run_op(self, op_type: CryptoOperationType, opid: UUID):
        """Run a performer for a single operation."""

        # Get a function to perform the op using adapters
        performer = self.registry.crypto_operation_performers.get(op_type)
        if not performer:
            raise RuntimeError("Doesn't have a performer for operation {}".format(op_type))

        logger.info("Running op: %s %s", op_type, opid)
        # Do the actual operation
        performer(self.web3, self.dbsession, opid)

        self.notify_op_complete(opid)

    def run_waiting_operations(self) -> Tuple[int, int]:
        """Run all operations that are waiting to be executed.

        :return: Number of operations (performed successfully, failed)
        """

        success_count = 0
        failure_count = 0

        ops = self.get_waiting_operation_ids()

        if ops:
            logger.info("%s operations in the queue", len(ops))

        for opid, op_type in ops:
            try:
                self.run_op(op_type, opid)
                success_count += 1
            except Exception as e:
                failure_count += 1
                logger.error("Crypto operation failure %s", e)
                logger.exception(e)
                raise

        return success_count, failure_count