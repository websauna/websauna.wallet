import logging

from typing import Iterable, Tuple, Union

from sqlalchemy.orm import Session
from web3 import Web3
from websauna.system.model.retry import retryable, ensure_transactionless

from websauna.wallet.ethereum.populusutils import get_rpc_client
from websauna.wallet.ethereum.utils import txid_to_bin, bin_to_txid
from websauna.wallet.events import CryptoOperationCompleted
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoOperationState


logger = logging.getLogger(__name__)


class DatabaseConfirmationUpdater:
    """Update confirmation counts for crypto operations requiring them."""

    def __init__(self, web3: Web3, dbsession: Session, network_id, registry, logger=logger):

        assert isinstance(web3, Web3)
        self.web3 = web3

        # web3 doesn't support filters yet
        self.client = get_rpc_client(web3)

        self.network_id = network_id
        self.dbsession = dbsession
        self.tm = self.dbsession.transaction_manager
        self.logger = logger
        self.registry = registry

    def _get_tm(*args, **kargs):
        """Get transaction manager needed to transaction retry."""
        self = args[0]
        return self.tm

    def scan_txs(self) -> Tuple[int, int]:
        """Look for new deposits.

        Assume addresses are hosted wallet smart contract addresses and scan for their event logs.

        :return: (performed updates, failed updates)
        """
        updates = failures = 0

        current_block = self.client.get_block_number()

        ensure_transactionless(self.tm)

        # Don't repeat update for the same block
        with self.tm:
            network = self.dbsession.query(AssetNetwork).get(self.network_id)
            last_block = network.other_data.get("last_database_confirmation_updater_block")

        if current_block == last_block:
            logger.debug("No new blocks, still on %d, skipping confirmation updater", current_block)
            return 0, 0

        ensure_transactionless(self.tm)

        txs = list(self.get_monitored_transactions())
        logger.debug("Block %d, updating confirmations for %d transactions", current_block, len(txs))

        ensure_transactionless(self.tm)

        for tx in txs:

            receipt = self.client.get_transaction_receipt(tx)
            txinfo = self.client.get_transaction_by_hash(tx)
            if not receipt:
                # This withdraw transaction is still in memory pool and has not been mined into a block yet
                continue

            try:
                new_updates, new_failures = self.update_tx(current_block, txinfo, receipt)
                updates +=  new_updates
                failures += new_failures
            except Exception as e:
                logger.error("Could not update transaction %s", tx)
                logger.exception(e)
                failures += 1

        with self.tm:
            network = self.dbsession.query(AssetNetwork).get(self.network_id)
            network.other_data["last_database_confirmation_updater_block"] = current_block

        ensure_transactionless(self.tm)

        return updates, failures

    @retryable(get_tm=_get_tm)
    def update_tx(self, current_block: int, txinfo: dict, receipt: dict) -> Tuple[int, int]:
        """Process logs from initial log run or filter updates.

        :return: (performed updates, failed updates)
        """

        # We may have multiple ops for one transaction
        ops = self.dbsession.query(CryptoOperation).filter_by(txid=txid_to_bin(receipt["transactionHash"]))
        updates = failures = 0

        for op in ops:

            # http://ethereum.stackexchange.com/q/6007/620
            if txinfo["gas"] == receipt["gasUsed"]:
                op.other_info["failure_reason"] = "Smart contract rejected the transaction"
                op.mark_failure()
                failures += 1

            # Withdraw operation has not gets it block yet
            # Block number may change because of the works
            assert receipt["blockNumber"].startswith("0x")
            op.block = int(receipt["blockNumber"], 16)

            confirmation_count = current_block - op.block
            if op.update_confirmations(confirmation_count):

                # Notify listeners we reached the goal
                logger.info("Completed, confirmations reached %s", op)
                self.registry.notify(CryptoOperationCompleted(op, self.registry, self.web3))

                updates += 1

        return updates, failures

    @retryable(get_tm=_get_tm)
    def get_monitored_transactions(self) -> Iterable[str]:
        """Get all transactions that are lagging behind the confirmation count."""
        result = set()

        # Transactions that are broadcasted
        txs = self.dbsession.query(CryptoOperation).filter(CryptoOperation.state == CryptoOperationState.broadcasted, CryptoOperation.network_id == self.network_id)
        for tx in txs:
            result.add(bin_to_txid(tx.txid))
        return result

    def poll(self) -> Tuple[int, int]:
        """Poll geth for transaction updates.

        Get new transaction receipts for all incomplete transactions pending confirmations and try to close these operations.

        :return: tuple(how many operations got confirmed, how many internal failures we had)
        """
        return self.scan_txs()
