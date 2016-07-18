"""Stateful poller Ethereum over RPC API to get contract events.

Using geth JSON RPC API: https://github.com/ethereum/wiki/wiki/JSON-RPC#eth_newfilter
"""


import time
import logging
from typing import Callable, Iterable, List, Optional
import datetime


from .ethjsonrpc import EthJsonRpc

from .utils import sha3

#: Default logger
_logger = logging.getLogger(__name__)


#: Called when we spot a fired event. Callback is (contract_address, event_signature_as_hex_string, api_data) -> True if the event was succesfully registered, False if duplicate/ignored
callback_type = Callable[[str, str, dict], bool]


class ContractStatus:
    """Hold information about the processing status of a single contract."""

    def __init__(self, filter_id, last_updated_at):
        self.filter_id = filter_id
        self.last_updated_at = last_updated_at


class BlockchainNotUpdating(Exception):
    pass


def now() -> datetime.datetime:
    """Get the current time as timezone-aware UTC timestamp."""
    return datetime.datetime.now(datetime.timezone.utc)


class ContractListener:
    """Fetch updates on events Solidy contract posts to Ethereum blockchain.

    This is a low level interface which monitors all events for given contracts. When we get new contract logs (events) over RPC API we post them to a callback that can translate them to human readable form. This listener only knows about raw hashes of event definition names.

    The poller is stateful and allows you to add and remove contracts in fly.
    """

    def __init__(self, client: EthJsonRpc, callback: callback_type, from_block=0, logger=_logger):
        """Create a contract listener.

        Callbacks look like:

        .. code-block:: python

            def cb(address, event_abi_signature, api_data)
                pass

        :param client: EthJsonRpc instance we use to connect to geth node
        :param callback: Callable that's going to get called for every new event detected.
        :param from_block: When to start iterating
        :param logger: Optional
        """
        self.logger = _logger
        self.client = client
        self.callback = callback
        self.from_block = from_block

        self.blockchain_timeout_seconds = 400

        #: Mapping contract address -> ContractStatus
        self.currently_monitored_contracts = {}

    def check_up_to_date(self):
        """Make sure that the node is connected to the blockchain."""

        # last_block = self.client.eth_blockNumber()["result"]
        block_info = self.client.eth_getBlockByNumber()
        assert block_info["number"]
        timestamp = int(block_info["timestamp"], 16)
        lag = time.time() - timestamp
        if lag > self.blockchain_timeout_seconds:
            raise BlockchainNotUpdating("Too long since the last block, {} seconds".format(lag))
        return block_info["number"]

    def install_filter(self, contract_address: str):
        """Set up event filtering for a single contract using eth_newFilter.

        :param contract_address: hex string
        """

        installed_filter_id = self.client.new_filter(from_block=0, address=contract_address)
        status = ContractStatus(filter_id=installed_filter_id, last_updated_at=None)
        self.currently_monitored_contracts[contract_address] = status

    def process_events(self, status: ContractStatus, changes: Optional[List[dict]]) -> int:
        """Process logs from initial log run or filter updates."""
        updates = 0

        # Nothing changed
        if changes is None:
            return 0

        for change in changes:

            contract_address = change["address"]

            topics = change["topics"]
            if not topics:
                self.logger.warn("Did not get topics with change data %s", change)
                continue

            # This is event signature as hex encoded string
            event_hash = topics[0]

            try:
                success = self.callback(contract_address, event_hash, change)
                if success:
                    updates += 1
            except Exception as e:
                # IF we have bad code for processing one contract, don't stop at that but keep pushing for others
                self.logger.error("Failed to update contract %s", contract_address)
                self.logger.exception(e)

        if status:
            status.last_updated_at = now()

        return updates

    def fetch_all(self, contract_address: str) -> int:

        assert type(contract_address) == str
        assert contract_address.startswith("0x")
        contract_address = contract_address.lower()

        # Signature different as for newFilter :(
        changes = self.client.get_logs(from_block=self.from_block, address=contract_address)

        self.logger.info("Received %d changes for a contract %s", len(changes), contract_address)

        return self.process_events(None, changes)

    def fetch_changes(self, contract) -> int:
        """Fetch latest events from geth.

        .. note ::

                The some transction might be posted twice due to ramp up and poll calls running differently.
                Always make sure callbacks handle this.

        :param contracts: List of contract addresses as hex string we are interested in

        :return: Number of callbacks made
        """
        status = self.currently_monitored_contracts[contract]
        filter_id = status.filter_id
        changes = self.client.get_filter_changes(filter_id=filter_id)
        return self.process_events(status, changes)

    def monitor_contract(self, contract_address) -> int:
        """Start monitoring a contract and run callback for its all past events.

        If contract is already added do nothing.

        :param contract_address:
        :return: Number of triggered callbacks
        """
        assert type(contract_address) == str
        assert contract_address.startswith("0x")
        contract_address = contract_address.lower()

        if contract_address in self.currently_monitored_contracts:
            return 0

        self.install_filter(contract_address)

        return self.fetch_all(contract_address)

    def remove_contract(self, contract_address):
        del self.currently_monitored_contracts["contract_address"]

    def get_current_block(self):
        # Current block.
        block_number = self.client.get_block_number()
        return block_number

    def poll(self) -> int:
        """Fetch changes to all monitored contracts.

        Note that some events might be posted twice due to time elapse between ``monitor_contract`` and ``poll``.

        :return: Number of triggered callbacks
        """
        updates = 0
        for c in self.currently_monitored_contracts.keys():
            updates += self.fetch_changes(c)

        return updates

