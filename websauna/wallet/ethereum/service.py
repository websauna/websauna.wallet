import threading
from typing import Iterable, List, Tuple
from uuid import UUID
import logging

import transaction
from eth_ipc_client import Client
from pyramid.registry import Registry

from sqlalchemy.orm import Session
from websauna.utils.time import now
from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.dbconfirmationupdater import DatabaseConfirmationUpdater
from websauna.wallet.ethereum.dbcontractlistener import EthWalletListener, EthTokenListener
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.interfaces import IOperationPerformer
from websauna.wallet.ethereum.token import get_token_contract_class
from websauna.wallet.ethereum.wallet import get_wallet_contract_class
from websauna.wallet.models import CryptoOperation, CryptoOperationState


logger = logging.getLogger(__name__)


class EthereumService:
    """Ethereum service takes care of synchronizing operations between internal database and Ethereum daemon.

    We take a simple approach where we have one service / db running one single thread which does all operations serial manner.

    When testing, we call functions directly.
    """

    def __init__(self, client: Client, asset_network_id: UUID, dbsession: Session, registry: Registry):
        self.client = client
        self.asset_network_id = asset_network_id
        self.dbsession = dbsession
        self.registry = registry

        self.setup_listeners()

    def get_withdraw_required_confirmation_count(self):
        """How many confirmations we check on withdraw ops until we mark them confirmed."""
        return 1

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
                        raise RuntimeError("Doesn't have a performer for operation {}".format(op))

                    logger.info("Running op: %s", op)

                    # Do the actual operation
                    performer(self, op)
                    success_count += 1

                except Exception as e:
                    failure_count += 1
                    logger.error("Crypto operation failure %s", e)
                    logger.exception(e)
                    raise

        return success_count, failure_count

    def setup_listeners(self):
        """Setup subsystems that scan for incoming events from geth."""
        wallet_contract = get_wallet_contract_class()
        token_contract = get_token_contract_class()
        self.eth_wallet_listener = EthWalletListener(self.client, wallet_contract, self.dbsession, self.asset_network_id)
        self.eth_token_listener = EthTokenListener(self.client, token_contract, self.dbsession, self.asset_network_id)
        self.confirmation_updater = DatabaseConfirmationUpdater(self.client, self.dbsession, self.asset_network_id)

    def run_listener_operations(self) -> Tuple[int, int]:
        """Return number of operations events read and handled."""
        total_success = total_failure = 0

        for func in (self.eth_wallet_listener.poll, self.eth_token_listener.poll):
            success, failure = func()
            total_success += success
            total_failure += failure

        return total_success, total_failure

    def run_confirmation_updates(self) -> Tuple[int, int]:
        return self.confirmation_updater.poll()

    def run_event_cycle(self) -> Tuple[int, int]:
        """Run full event cycle for all operations."""
        total_success = total_failure = 0

        for func in (self.run_waiting_operations, self.run_listener_operations, self.run_confirmation_updates):
            success, failure = func()
            total_success += success
            total_failure += failure

        return total_success, total_failure


