import os
import threading
from typing import Tuple
from uuid import UUID
import logging
import json
import time

import sys
import transaction
from web3 import Web3, RPCProvider
from pyramid.registry import Registry

from sqlalchemy.orm import Session

from websauna.system.model.meta import create_dbsession
from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.dbconfirmationupdater import DatabaseConfirmationUpdater
from websauna.wallet.ethereum.dbcontractlistener import EthWalletListener, EthTokenListener
from websauna.wallet.ethereum.dboperationqueue import OperationQueueManager

from websauna.wallet.ethereum.geth import start_private_geth
from websauna.wallet.ethereum.token import Token
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models.heartbeat import update_heart_beat

logger = logging.getLogger(__name__)


class EthereumService:
    """Ethereum service takes care of synchronizing operations between internal database and Ethereum daemon.

    We take a simple approach where we have one service / db running one single thread which does all operations serial manner.

    When testing, we call functions directly.
    """

    def __init__(self, web3: Web3, asset_network_id: UUID, dbsession: Session, registry: Registry):

        assert isinstance(web3, Web3)
        assert isinstance(registry, Registry)
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
        self.eth_wallet_listener = EthWalletListener(self.web3, wallet_contract, self.dbsession, self.asset_network_id, registry=self.registry)
        self.eth_token_listener = EthTokenListener(self.web3, token_contract, self.dbsession, self.asset_network_id, registry=self.registry)
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

        update_heart_beat(self.dbsession, self.asset_network_id)

        return total_success, total_failure



class ServiceThread(threading.Thread):
    
    def __init__(self, request, name, config: dict):
        super(ServiceThread, self).__init__(name=name)
        self.request = request
        self.name = name
        self.config = config
        self.killed = False

    def unlock(self, web3, password=):
        """Unlock coinbase account."""

        # Allow access to sendTransaction() to use coinbase balance
        # to deploy contracts. Password is from py-geth
        # default_blockchain_password file. Assume we don't
        # run tests for more than 9999 seconds
        coinbase = web3.eth.coinbase
        success = web3.personal.unlockAccount(
            coinbase,
            passphrase=password,
            duration=24*3600)

        if not success:
            raise RuntimeError("Cannot unlock coinbase account: {}".format())
        
    def run(self):
        # Configure dbsession per thread
        request = self.request
        dbsession = create_dbsession(request.registry)

        host = self.config["host"]
        port = self.config["port"]
        web3 = Web3(RPCProvider(host, port))

        with transaction.manager:
            network = get_eth_network(dbsession, self.name)
            network_id = network.id

        chains_dir = request.registry.settings["ethereum.chains_dir"]

        if self.config["private_geth"]:
            # Start private geth instance to connect to
            chain_dir = os.path.join(chains_dir, self.name.replace(" ", "-"))
            start_private_geth(self.name.replace(" ", "-"), chain_dir, host, port)
            time.sleep(2)  # Give geth time to wake up

        service = EthereumService(web3, network_id, dbsession, request.registry)

        sleepy = int(request.registry.settings.get("ethereum.daemon_poll_seconds", 2))

        while not self.killed:
            try:
                service.run_event_cycle()
            except Exception as e:
                logger.error("Dying, because of %s", e)
                logger.exception(e)
                return

            logger.info("Service event cycled")
            time.sleep(sleepy)


def run_services(request):
    """Start a network service.

    We are connecting to multiple networks. Start one thread per network.
    """

    # Load network configuration to which networks we should connect to
    services = request.registry.settings.get("ethereum.network_configuration")

    try:
        services = json.loads(services)
    except json.decoder.JSONDecodeError as e:
        raise RuntimeError("Could not decode: {}".format(services)) from e

    threads = []
    for name, config in services.items():
        t = ServiceThread(request, name, config)
        t.start()
        threads.append(t)

    # Main loop
    started = time.time()
    shown_start_message = False
    while True:

        for t in threads:
            if not t.is_alive():
                # One thread died, kill all of them
                for t in threads:
                    t.killed = True

                sys.exit("One of service threads had died, quitting")

        # If everybody is alive after 5 seconds consider it a succesful start
        if time.time() > started + 5 and not shown_start_message:
            # Mainly picked up by tests, other similar things
            logger.info("Ethereum service started")
            shown_start_message = True

        time.sleep(1)