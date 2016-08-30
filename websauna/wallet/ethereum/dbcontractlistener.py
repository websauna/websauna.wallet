import logging

from typing import Iterable, Optional, List, Tuple

import transaction
from decimal import Decimal
from eth_ipc_client import Client
from sqlalchemy.orm import Session
from web3 import Web3

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.populuslistener import get_contract_events
from websauna.wallet.ethereum.populusutils import get_rpc_client
from websauna.wallet.ethereum.utils import bin_to_eth_address, txid_to_bin, wei_to_eth, eth_address_to_bin
from websauna.wallet.events import IncomingCryptoDeposit
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoAddressDeposit
from websauna.wallet.models import Account
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import Asset
from websauna.wallet.models.blockchain import CryptoOperationType

logger = logging.getLogger(__name__)


class DatabaseContractListener:
    """Contract listener that gets the monitored contracts from database."""

    def __init__(self, web3: Web3, contract: type, dbsession: Session, network_id, from_block=0, confirmation_count=1, logger=logger, registry=None):

        assert isinstance(web3, Web3)

        self.web3 = web3

        self.client = get_rpc_client(web3)

        self.last_block = from_block
        self.network_id = network_id
        self.event_map = self.build_event_map(contract)
        self.contract = contract
        self.dbsession = dbsession
        self.logger = logger
        self.confirmation_count = confirmation_count

        # For event notifications
        self.registry = registry

    def build_event_map(self, contract: type) -> dict:
        """Map log hashes to Populus contract event objects."""
        events = get_contract_events(contract)

        # Parsed hex string -> event mappings.
        # We parse to avoid padding zero issues.
        event_map = {signature: event for signature, event in events}
        return event_map

    def scan_logs(self, from_block, to_block) -> Tuple[int, int]:
        """Look for new deposits.

        Assume addresses are hosted wallet smart contract addresses and scan for their event logs.
        """
        addresses = list(self.get_monitored_addresses())
        if not addresses:
            return 0, 0
        logs = self.client.get_logs(from_block=from_block, to_block=to_block, address=addresses)
        return self.process_logs(logs)

    def process_logs(self, changes: Optional[List[dict]]) -> Tuple[int, int]:
        """Process logs from initial log run or filter updates."""
        updates = failures = 0

        # Nothing changed
        if changes is None:
            return 0, 0

        for change in changes:

            contract_address = change["address"]

            topics = change["topics"]
            if not topics:
                self.logger.warn("Did not get topics with change data %s", change)
                continue

            # This is event signature as hex encoded string
            event_hash = topics[0]

            try:
                if self.process_log(contract_address, event_hash, change):
                    updates += 1
            except Exception as e:
                # IF we have bad code for processing one contract, don't stop at that but keep pushing for others
                self.logger.error("Failed to update contract %s", contract_address)
                self.logger.exception(e)
                failures += 1

        return updates, failures

    def parse_log_data(self, signature: str, log_entry) -> Tuple[str, dict]:
        """Parse raw EVM log binary to a human readable format using contract ABI."""
        event = self.event_map.get(int(signature, 16))
        assert event, "Signature {} not in event map {}".format(signature, self.event_map)
        log_data = event.get_log_data(log_entry, indexed=True)
        return event.name, log_data

    def process_log(self, contract_address, event_hash: str, change: dict):
        event_name, log_data = self.parse_log_data(event_hash, change)
        return self.handle_event(event_name, contract_address, log_data, change)

    def poll(self) -> int:
        """Scan blocks for new events.

        Remember the last scanned block and start from there on next poll().
        """
        current_block = self.client.get_block_number()
        update_count, failure_count = self.scan_logs(self.last_block, current_block)
        self.last_block = current_block
        return update_count, failure_count

    def force_scan(self, from_block, to_block):
        """Scan certain range of block for certain events.

        Rescanning a block should not result to double database entries.
        """
        return self.scan_logs(from_block, to_block)

    def get_unique_transaction_id(self, log_entry: dict) -> bytes:
        """Get txid - logindex pair.

        Because ethereum transactions may contain several log events due to cross contract calls, it's not enough to identify events by their transaction hash. Instead, we use tranaction hash - log index pair."""
        txid = txid_to_bin(log_entry["transactionHash"])
        logIndex = int(log_entry["logIndex"], 16)
        assert logIndex < 256
        data = txid + bytes([logIndex])
        assert len(data) < 34
        return data

    def get_existing_op(self, opid: bytes, op_type: CryptoOperationType) -> CryptoOperation:
        """Check if we have already crypto operation in process for this event identified by transaction hash + log index"""

        #: TODO: Ignore_op_type as one log entry should not be able to generate two operations
        return self.dbsession.query(CryptoOperation).filter_by(opid=opid).one_or_none()

    def handle_event(self, event_name: str, contract_address: str, log_data: dict, log_entry: dict) -> bool:
        """Handle incoming smart contract event.

        :param event_name: Event name as it appears in Solidity, without ABI parameters
        :param log_data: Parsed event data using the contract ABI
        :param log_entry: Raw log data from Geth
        :return: True if this event resulted to database changes
        """
        raise NotImplementedError()

    def get_monitored_addresses(self):
        raise NotImplementedError()

    def notify_deposit(self, op):
        """Notify new deposits incoming."""
        if self.registry is not None:
            self.registry.notify(IncomingCryptoDeposit(op, self.registry, self.web3))


class EthWalletListener(DatabaseContractListener):
    """Listen Events send by Hosted Wallet contract.

    Contract points to a hosted wallet contract.
    """

    def get_monitored_addresses(self) -> Iterable[str]:
        """Get list of all ETH crtypto deposit addresses."""
        with transaction.manager:
            for addr in self.dbsession.query(CryptoAddress, CryptoAddress.address).filter(CryptoAddress.network_id == self.network_id, CryptoAddress.address != None):
                # addr.address is not set if the address is under construction
                yield bin_to_eth_address(addr.address)

    def handle_event(self, event_name: str, contract_address: str, log_data: dict, log_entry: dict):
        """Map incoming EVM log to database entry."""

        with transaction.manager:
            opid = self.get_unique_transaction_id(log_entry)

            existing_op = self.get_existing_op(opid, CryptoOperationType.deposit)
            if existing_op:
                # Already in the database, all we need to do is to call blocknumber updater now
                return False

            network = self.dbsession.query(AssetNetwork).get(self.network_id)
            address = self.dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(contract_address), network=network).one()

            op = self.create_op(event_name, address, opid, log_data, log_entry)
            if not op:
                # This was an event we don't care about
                return False

            op.opid = opid
            op.txid = txid_to_bin(log_entry["transactionHash"])
            op.block = int(log_entry["blockNumber"], 16)
            op.required_confirmation_count = self.confirmation_count
            self.dbsession.add(op)

            self.notify_deposit(op)

            return True

    def create_op(self, event_name: str, address: CryptoAddress, opid: bytes, log_data: dict, log_entry: dict) -> Optional[CryptoOperation]:
        """Create new database cryptoperation matching the new event."""
        func_name = "on_" + event_name.lower()
        func = getattr(self, func_name, None)

        # This is an event we have a handler for and looking forward to modify our database based on it (Deposit)
        if func:
            return func(address, opid, log_data, log_entry)
        else:
            # Execute, etc. event we are not interested in this time
            return None

    def on_deposit(self, address: CryptoAddress, opid, log_data, log_entry) -> CryptoAddressDeposit:
        """Handle Hosted Wallet Deposit event.

        Create incoming holding account holding the ETH assets until we receive enough confirmations.
        """

        op = CryptoAddressDeposit(address.network)

        # Get or create final account where we deposit the transaction
        asset = get_ether_asset(self.dbsession)
        crypto_account = address.get_or_create_account(asset)
        op.crypto_account = crypto_account

        op.external_address = eth_address_to_bin(log_data["from"])

        # Create holding account that keeps the value until we receive N amount of confirmations
        acc = Account(asset=asset)
        self.dbsession.add(acc)
        self.dbsession.flush()

        value = wei_to_eth(log_data["value"])
        acc.do_withdraw_or_deposit(value, "ETH deposit from {} in tx {}".format(log_data["from"], log_entry["transactionHash"]))

        op.holding_account = acc
        return op

    def on_failedeexcute(self, address: CryptoAddress, opid, log_data, log_entry) -> CryptoAddressDeposit:
        """Calling a contract from hosted wallet failed."""
        # TODO
        self.logger.error("failedexecute")


class EthTokenListener(DatabaseContractListener):
    """Listen token transfers."""

    def get_monitored_addresses(self) -> Iterable[str]:
        """Get list of all known token smart contract addresses."""
        with transaction.manager:
            for asset in self.dbsession.query(Asset, Asset.external_id).filter(Asset.network_id == self.network_id, Asset.external_id != None):
                yield bin_to_eth_address(asset.external_id)

    def handle_event(self, event_name: str, contract_address: str, log_data: dict, log_entry: dict):
        """Map incoming EVM log to database entry."""

        with transaction.manager:

            opid = self.get_unique_transaction_id(log_entry)

            existing_op = self.get_existing_op(opid, CryptoOperationType.deposit)
            if existing_op:
                # Already in the database, all we need to do is to call blocknumber updater now
                return False

            network = self.dbsession.query(AssetNetwork).get(self.network_id)
            asset = self.dbsession.query(Asset).filter_by(network=network, external_id=eth_address_to_bin(contract_address)).one()

            if event_name == "Transfer":

                to_address = eth_address_to_bin(log_data["to"])
                from_address = eth_address_to_bin(log_data["from"])
                value = Decimal(log_data["value"])

                # Get destination address entry
                address = self.dbsession.query(CryptoAddress).filter_by(address=to_address).one_or_none()
                if not address:
                    # Address not in our system
                    return False

                # Create operation
                op = CryptoAddressDeposit(network=network)
                op.opid = opid
                op.txid = txid_to_bin(log_entry["transactionHash"])
                op.external_address = from_address
                op.block = int(log_entry["blockNumber"], 16)
                op.required_confirmation_count = self.confirmation_count
                op.crypto_account = address.get_or_create_account(asset)

                # Create holding account that keeps the value until we receive N amount of confirmations
                acc = Account(asset=asset)
                self.dbsession.add(acc)
                self.dbsession.flush()

                acc.do_withdraw_or_deposit(value, "Token {} deposit from {} in tx {}".format(asset.symbol, log_data["from"], log_entry["transactionHash"]))
                op.holding_account = acc
                self.dbsession.add(op)

                self.notify_deposit(op)

                return True
            else:
                # Unmonitored event
                return False
