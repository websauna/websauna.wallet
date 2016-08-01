import threading
from typing import Iterable, List, Tuple
from uuid import UUID
import logging

import transaction
from eth_ipc_client import Client
from web3 import Web3
from pyramid.registry import Registry

from sqlalchemy.orm import Session
from websauna.utils.time import now
from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.dbconfirmationupdater import DatabaseConfirmationUpdater
from websauna.wallet.ethereum.dbcontractlistener import EthWalletListener, EthTokenListener
from websauna.wallet.ethereum.dboperationqueue import OperationQueueManager
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.interfaces import IOperationPerformer
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import CryptoOperation, CryptoOperationState


logger = logging.getLogger(__name__)


class EthereumService:
    """Ethereum service takes care of synchronizing operations between internal database and Ethereum daemon.

    We take a simple approach where we have one service / db running one single thread which does all operations serial manner.

    When testing, we call functions directly.
    """

    def __init__(self, web3: Web3, asset_network_id: UUID, dbsession: Session, registry: Registry):

        assert isinstance(web3, Web3)
        self.web3 = web3

        self.asset_network_id = asset_network_id
        self.dbsession = dbsession
        self.registry = registry

        self.setup_listeners()

    def get_withdraw_required_confirmation_count(self):
        """How many confirmations we check on withdraw ops until we mark them confirmed."""
        return 1

    def setup_listeners(self):
        """Setup subsystems that scan for incoming events from geth."""
        wallet_contract = HostedWallet.contract_class(self.web3)
        token_contract = Token.contract_class(self.web3)
        self.eth_wallet_listener = EthWalletListener(self.web3, wallet_contract, self.dbsession, self.asset_network_id)
        self.eth_token_listener = EthTokenListener(self.web3, token_contract, self.dbsession, self.asset_network_id)
        self.confirmation_updater = DatabaseConfirmationUpdater(self.web3, self.dbsession, self.asset_network_id)
        self.op_queue_manager = OperationQueueManager(self.web3, self.dbsession, self.asset_network_id, self.registry)

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

    def run_waiting_operations(self) -> Tuple[int, int]:
        """Run all operations that are waiting to be executed.

        :return: Number of operations (performed successfully, failed)
        """
        return self.op_queue_manager.run_waiting_operations()

    def run_event_cycle(self) -> Tuple[int, int]:
        """Run full event cycle for all operations."""
        total_success = total_failure = 0

        for func in (self.run_waiting_operations, self.run_listener_operations, self.run_confirmation_updates):
            success, failure = func()
            total_success += success
            total_failure += failure

        return total_success, total_failure


