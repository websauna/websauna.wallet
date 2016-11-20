import os
import signal
import threading
import logging
import json
import time
import sys
from typing import Tuple
from uuid import UUID

from web3 import Web3
from web3.providers.rpc import KeepAliveRPCProvider
from pyramid.registry import Registry
from sqlalchemy.orm import Session
from websauna.system.http import Request

from websauna.system.model.meta import create_dbsession
from websauna.system.model.retry import ensure_transactionless

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
        self.confirmation_updater = DatabaseConfirmationUpdater(self.web3, self.dbsession, self.asset_network_id, self.registry)
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

    def update_heartbeat(self):
        # Tell web interface we are still alive

        block_number = self.web3.eth.blockNumber
        block = self.web3.eth.getBlock(block_number)
        block_time = int(block["timestamp"])
        update_heart_beat(self.dbsession, self.asset_network_id, block_number, block_time)

    def run_event_cycle(self, cycle_num=None) -> Tuple[int, int]:
        """Run full event cycle for all operations."""
        total_success = total_failure = 0

        for func in (self.run_waiting_operations, self.run_listener_operations, self.run_confirmation_updates):
            # Make sure all transactions are closed before and after running ops
            # logger.info("Running %s", func)
            ensure_transactionless("TX management Error. Starting to process {} in event cycle {}".format(func, cycle_num))
            success, failure = func()
            ensure_transactionless()
            total_success += success
            total_failure += failure

        self.update_heartbeat()

        return total_success, total_failure


class ServiceCore:
    """Provide core functionality for inline, threaded or processed services."""

    def __init__(self, request, name, config: dict, require_unlock=True):

        self.request = request
        self.name = name
        self.config = config
        self.service = None
        self.geth = None  # Running private geth testnet process

        #: Do coinbase account unlock test
        self.require_unlock = require_unlock

    def unlock(self, web3, password):
        """Unlock coinbase account."""

        # Allow access to sendTransaction() to use coinbase balance
        # to deploy contracts. Password is from py-geth
        # default_blockchain_password file. Assume we don't
        # run tests for more than 9999 seconds
        coinbase = web3.eth.coinbase
        success = web3.personal.unlockAccount(
            coinbase,
            passphrase=password,
            duration=24 * 3600)

        if not success:
            raise RuntimeError("Cannot unlock coinbase account: {}".format(self.config))

    def start_geth(self):

        if self.config["private_geth"]:

            chains_dir = self.request.registry.settings["ethereum.chains_dir"]

            host = self.config["host"]
            port = int(self.config["port"])
            p2p_port = int(self.config.get("p2p_port", 30303))

            # Start private geth instance to connect to
            chain_dir = os.path.join(chains_dir, self.name.replace(" ", "-"))
            geth = start_private_geth(self.name.replace(" ", "-"), chain_dir, host, port, p2p_port=p2p_port)
            time.sleep(2)  # Give geth time to wake up
        else:
            geth = None
        return geth

    def check_account_locked(self, web3, account):
        # http://ethereum.stackexchange.com/a/6960/620
        try:
            web3.eth.sendTransaction({"from": account, "to": account, "value": 1, "gas": 30000})
        except Exception as e:
            raise RuntimeError("Coinbase account locked on {}? {}. Cannot start.".format(self.name, str(e))) from e

    def do_unlock(self):

        if not self.require_unlock:
            return

        # Optionally unlock the geth instance
        passwd = self.config.get("coinbase_password", None)
        if passwd is not None:

            if passwd == "":
                raise RuntimeError("Cannot have empty coinbase password")

            self.unlock(self.web3, passwd)

        # Check if account is still locked and bail out
        # self.check_account_locked(self.web3, self.web3.eth.coinbase)

    def create_web3(self):
        host = self.config["host"]
        port = int(self.config["port"])
        web3 = Web3(KeepAliveRPCProvider(host, port, connection_timeout=60, network_timeout=60))
        return web3

    def setup(self, dbsession=None):
        request = self.request

        if not dbsession:
            dbsession = create_dbsession(request.registry)

        logger.info("Setting up Ethereum service %s with dbsession %s", self, dbsession)

        self.web3 = self.create_web3()

        with dbsession.transaction_manager:
            network = get_eth_network(dbsession, self.name)
            network_id = network.id

        self.geth = self.start_geth()
        self.service = EthereumService(self.web3, network_id, dbsession, request.registry)
        self.do_unlock()

        logger.info("setup() complete")

    def run_cycle(self, cycle_num=None):
        """Run one event cycle.

        :param cycle_num: Optional integer of the number of cycles since the start of this process. Used in debug logging.
        """

        geth = self.geth
        service = self.service

        if geth:
            if not geth.is_alive:
                raise RuntimeError("Geth died upon us")

        service.run_event_cycle(cycle_num)

    @classmethod
    def parse_network_config(cls, request):
        # Load network configuration to which networks we should connect to
        services = request.registry.settings.get("ethereum.network_configuration")

        try:
            services = json.loads(services)
        except json.decoder.JSONDecodeError as e:
            raise RuntimeError("Could not decode: {}".format(services)) from e

        return services


class ServiceThread(ServiceCore, threading.Thread):
    
    def __init__(self, request, name, config: dict):
        threading.Thread.__init__(self, name=name)
        ServiceCore.__init__(self, request, name, config)
        self.killed = False

    def run(self):
        # Configure dbsession per thread

        self.setup()

        sleepy = int(self.request.registry.settings.get("ethereum.daemon_poll_seconds", 2))
        cycle = 1
        geth = self.geth

        try:
            while not self.killed:
                logger.debug("Ethereum service %s event cycle %d, last block is %d", self.name, cycle, self.service.web3.eth.blockNumber)
                self.run_cycle(cycle)
                time.sleep(sleepy)
                cycle += 1
        finally:
            if geth:
                geth.stop()


class OneShot(ServiceCore):
    """Run service cycle only once.

    Useful for debugging.
    """

    def run_shot(self):

        self.setup(self.request.dbsession)

        try:
            self.run_cycle()
        finally:
            if self.geth:
                self.geth.stop()


def one_shot(request, network_name):
    """Single threaded one debug shot agaist the db state."""

    # Load network configuration to which networks we should connect to
    services = ServiceCore.parse_network_config(request)
    one_shot = OneShot(request, network_name, services[network_name])
    one_shot.run_shot()


def get_network_web3(request: Request, network_name: str) -> Web3:
    """Get a hold of configured web3.

    Useful for Celery tasks, etc.
    """
    services = ServiceCore.parse_network_config(request)
    one_shot = OneShot(request, network_name, services[network_name])
    return one_shot.create_web3()


#: Active threads
threads = []

#: We have been signalled to quit
interrupted = False


def exit_gracefully(signum, frame):
    global interrupted
    logger.error("Signalled to quit")
    for t in threads:
        t.killed = True
    interrupted = True


def run_services(request):
    """Start a network service.

    We are connecting to multiple networks. Start one thread per network.
    """
    global threads

    services = ServiceCore.parse_network_config(request)

    threads = []
    for name, config in services.items():
        t = ServiceThread(request, name, config)
        t.start()
        threads.append(t)

    # Main loop
    started = time.time()
    shown_start_message = False

    logger.info("Running threads %s", threads)

    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    while not interrupted:

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

