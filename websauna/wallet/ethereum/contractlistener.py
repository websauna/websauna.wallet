"""Poll Ethereum blockchain, install log hooks to call contracts.

Using geth JSON RPC API: https://github.com/ethereum/wiki/wiki/JSON-RPC#eth_newfilter

Copyright 2016 Mikko Ohtamaa - Licensed under MIT license.
"""


import time
import logging
from typing import Callable, Iterable, List, Optional
import datetime


from .ethjsonrpc import EthJsonRpc

from .utils import sha3

#: Default logger
_logger = logging.getLogger(__name__)


#: Called when we spot a fired event. Callback is (contract_address, event_signature, api_data) -> True if the event was succesfully registered, False if duplicate/ignored
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


def calculate_event_signature(decl: str) -> str:
    """Calculate bytecode signature of an event Solidy declaration.

    Example:

    .. code-block:

        assert calculate_event_signature("VerifyTokenSet(address,uint256)") == "3D2E225F28C7AAA8014B84B0DD267E297CB25A0B24CB02AB9C9FCF76F660F05F"

    To verify signature from the contract push opcodes:

    .. code-block:: console

        solc contract.sol --asm

    To debug transactions on Morden testnet

    * https://morden.ether.camp/transaction/9685191fece0dd0ef5a02210a305738be3fceb4089003924bc53de0cce0c0103

    http://solidity.readthedocs.io/en/latest/contracts.html#events

    https://github.com/ethereum/wiki/wiki/Solidity-Features#events
    """
    return "0x" + sha3(decl.encode("utf-8")).hex().lower()


class ContractListener:
    """Fetch updates on events Solidy contract posts to Ethereum blockchain.

    """

    def __init__(self, client: EthJsonRpc, events: Iterable[str], callback: callback_type, from_block=0, logger=_logger):
        """Create a contract listener.

        Callbacks look like:

        .. code-block:: python

            def cb(address, event, api_data)
                pass

        :param client: EthJsonRpc instance we use to connect to geth node
        :param events: List of Solidy event signatures we want to listne like like ``["Transfer(address,address,uint256)]``
        :param callback: Callable that's going to get called for every new event detected.
        :param from_block: When to start iterating
        :param logger: Optional
        """
        self.logger = _logger
        self.client = client
        self.events = events
        self.callback = callback
        self.from_block = from_block
        self.event_signatures = {calculate_event_signature(e): e for e in events}

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

        installed_filter_id = self.client.eth_newFilter(from_block=0, address=contract_address)
        status = ContractStatus(filter_id=installed_filter_id, last_updated_at=None)
        self.currently_monitored_contracts[contract_address] = status

    def process_events(self, status: ContractStatus, changes: Optional[List[dict]]) -> int:

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

            event_type = topics[0]
            if event_type not in self.event_signatures:
                self.logger.warn("Unknown event signature %s", change)
                continue

            try:
                success = self.callback(contract_address, self.event_signatures[event_type], change)
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
        changes = self.client.eth_getLogs(dict(fromBlock=self.from_block, address=contract_address))

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
        changes = self.client.eth_getFilterChanges(filter_id=filter_id)
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
        block_number = self.client.eth_blockNumber()
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
