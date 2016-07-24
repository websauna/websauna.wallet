import logging

from typing import Iterable, Optional, List, Tuple

import transaction
from eth_ipc_client import Client
from sqlalchemy.orm import Session

from websauna.wallet.ethereum.asset import get_ether_asset
from websauna.wallet.ethereum.populusutils import get_contract_events
from websauna.wallet.ethereum.utils import bin_to_eth_address, txid_to_bin, wei_to_eth, eth_address_to_bin
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoAddressDeposit
from websauna.wallet.models import Account
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import Asset


logger = logging.getLogger(__name__)


class DatabaseContractListener:
    """Contract listener that gets the monitored contracts from database."""

    def __init__(self, client: Client, contract: type, dbsession: Session, network_id, from_block=0, confirmation_count=1, logger=logger):
        self.client = client
        self.last_block = from_block
        self.network_id = network_id
        self.event_map = self.build_event_map(contract)
        self.contract = contract
        self.dbsession = dbsession
        self.logger = logger
        self.confirmation_count = confirmation_count

    def build_event_map(self, contract: type) -> dict:
        """Map log hashes to Populus contract event objects."""
        events = get_contract_events(contract)

        # Parsed hex string -> event mappings.
        # We parse to avoid padding zero issues.
        event_map = {int(signature, 16): event for signature, event in events}

        return event_map

    def scan_logs(self, from_block, to_block):
        """Look for new deposits.

        Assume addresses are hosted wallet smart contract addresses and scan for their event logs.
        """
        addresses = list(self.get_monitored_addresses())
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
                self.process_log(contract_address, event_hash, change)
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
        self.handle_event(event_name, contract_address, log_data, change)

    def poll(self) -> int:
        current_block = self.client.get_block_number()
        update_count, failure_count = self.scan_logs(self.last_block, current_block)
        self.last_block = current_block
        return update_count, failure_count

    def get_unique_transaction_id(self, log_entry: dict) -> bytes:
        """Get txid - logindex pair.

        Because ethereum transactions may contain several log events due to cross contract calls, it's not enough to identify events by their transaction hash. Instead, we use tranaction hash - log index pair."""
        txid = txid_to_bin(log_entry["transactionHash"])
        logIndex = int(log_entry["logIndex"], 16)
        assert logIndex < 256
        data = txid + bytes([logIndex])
        assert len(data) < 34
        return data

    def get_existing_op(self, opid: bytes):
        return self.dbsession.query(CryptoOperation).filter_by(opid=opid).one_or_none()

    def handle_event(self, contract_address, log_data):
        raise NotImplementedError()

    def get_monitored_addresses(self):
        raise NotImplementedError()


class EthWalletListener(DatabaseContractListener):
    """Listen Events send by Hosted Wallet contract.

    Contract points to a hosted wallet contract.
    """

    def get_monitored_addresses(self) -> Iterable[str]:
        """Get list of all ETH crtypto deposit addresses."""
        with transaction.manager:
            for addr in self.dbsession.query(CryptoAddress, CryptoAddress.address).filter(CryptoAddress.network_id == self.network_id):
                yield bin_to_eth_address(addr.address)

    def handle_event(self, event_name, contract_address, log_data: dict, log_entry: dict):
        """Map incoming EVM log to database entry."""
        with transaction.manager:
            opid = self.get_unique_transaction_id(log_entry)

            existing_op = self.get_existing_op(opid)
            if existing_op:
                # Already in the database, all we need to do is to call blocknumber updater now
                return

            network = self.dbsession.query(AssetNetwork).get(self.network_id)
            address = self.dbsession.query(CryptoAddress).filter_by(address=eth_address_to_bin(contract_address), network=network).one()

            op = self.create_op(event_name, address, opid, log_data, log_entry)
            op.opid = opid
            op.txid = txid_to_bin(log_entry["transactionHash"])
            op.address = address
            op.block = int(log_entry["blockNumber"], 16)
            op.required_confirmation_count = self.confirmation_count
            self.dbsession.add(op)

    def create_op(self, event_name: str, address: CryptoAddress, opid: bytes, log_data: dict, log_entry: dict) -> CryptoOperation:
        """Create new database cryptoperation matching the new event."""
        func_name = "on_" + event_name.lower()
        func = getattr(self, func_name)
        return func(address, opid, log_data, log_entry)

    def on_deposit(self, address: CryptoAddress, opid, log_data, log_entry) -> CryptoAddressDeposit:

        op = CryptoAddressDeposit(address.network)

        # Get or create final account where we deposit the transaction
        asset = get_ether_asset(self.dbsession)
        crypto_account = address.get_or_create_account(asset)
        op.crypto_account = crypto_account

        # Create holding account that keeps the value until we receive N amount of confirmations
        acc = Account(asset=asset)
        self.dbsession.add(acc)
        self.dbsession.flush()

        value = wei_to_eth(log_data["value"])
        acc.do_withdraw_or_deposit(value, "ETH deposit from {} in tx {}".format(log_data["from"].decode("utf-8"), log_entry["transactionHash"]))

        op.holding_account = acc
        return op




