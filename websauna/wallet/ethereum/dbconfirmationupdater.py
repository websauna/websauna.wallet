import logging

from typing import Iterable, Optional, List, Tuple

import transaction
from eth_ipc_client import Client
from sqlalchemy.orm import Session

from websauna.wallet.ethereum.utils import txid_to_bin, bin_to_txid
from websauna.wallet.models import CryptoOperation


logger = logging.getLogger(__name__)


class DatabaseConfirmationUpdater:
    """Update confirmation counts for crypto operations requiring them."""

    def __init__(self, client: Client, dbsession: Session, network_id, logger=logger):
        self.client = client
        self.network_id = network_id
        self.dbsession = dbsession
        self.logger = logger

    def scan_txs(self) -> Tuple[int, int]:
        """Look for new deposits.

        Assume addresses are hosted wallet smart contract addresses and scan for their event logs.
        """
        updates = failures = 0
        txs = list(self.get_monitored_transactions())

        current_block = self.client.get_block_number()
        for tx in txs:
            receipt = self.client.get_transaction_receipt(tx)
            try:
                if self.update_tx(current_block,  receipt):
                    updates +=1
            except Exception as e:
                logger.error("Could not update transaction %s", tx)
                logger.exception(e)
                failures += 1

        return updates, failures

    def update_tx(self, current_block: int, receipt: dict) -> bool:
        """Process logs from initial log run or filter updates."""

        with transaction.manager:

            # We may have multiple ops for one transaction
            ops = self.dbsession.query(CryptoOperation).filter_by(txid=txid_to_bin(receipt["transactionHash"]))

            for op in ops:
                assert op.block <= current_block
                confirmation_count = current_block - op.block

                return op.update_confirmations(confirmation_count)

    def get_monitored_transactions(self) -> Iterable[str]:
        """Get all transactions that are lagging behind the confirmation count."""
        result = []
        with transaction.manager:
            txs = self.dbsession.query(CryptoOperation).filter(CryptoOperation.required_confirmation_count != None, CryptoOperation.completed_at == None)
            for tx in txs:
                result.append(bin_to_txid(tx.txid))
        return result

    def poll(self) -> Tuple[int, int]:
        """Poll geth for transaction updates.

        Get new transaction receipts for all incomplete transactions pending confirmations and try to close these operations.

        :return: tuple(how many operations got confirmed, how many internal failures we had)
        """
        return self.scan_txs()
