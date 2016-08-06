import logging

from typing import Iterable, Tuple, Union

import transaction
from sqlalchemy.orm import Session
from web3 import Web3
from websauna.system.model.retry import retryable

from websauna.wallet.ethereum.populusutils import get_rpc_client
from websauna.wallet.ethereum.utils import txid_to_bin, bin_to_txid
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import CryptoOperationState


logger = logging.getLogger(__name__)


class DatabaseConfirmationUpdater:
    """Update confirmation counts for crypto operations requiring them."""

    def __init__(self, web3: Web3, dbsession: Session, network_id, logger=logger):

        assert isinstance(web3, Web3)
        self.web = web3

        # web3 doesn't support filters yet
        self.client = get_rpc_client(web3)

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
            txinfo = self.client.get_transaction_by_hash(tx)
            if not receipt:
                # This withdraw transaction is still in memory pool and has not been mined into a block yet
                continue

            try:
                result = self.update_tx(current_block, txinfo, receipt)
                if result is True:
                    updates +=1
                elif result == "fail":
                    failures += 1
            except Exception as e:
                logger.error("Could not update transaction %s", tx)
                logger.exception(e)
                failures += 1

        return updates, failures

    @retryable
    def update_tx(self, current_block: int, txinfo: dict, receipt: dict) -> Union[bool, str]:
        """Process logs from initial log run or filter updates."""

        # We may have multiple ops for one transaction
        ops = self.dbsession.query(CryptoOperation).filter_by(txid=txid_to_bin(receipt["transactionHash"]))

        for op in ops:

            # http://ethereum.stackexchange.com/q/6007/620
            if txinfo["gas"] == receipt["gasUsed"]:
                op.other_info["failure_reason"] = "Smart contract rejected the transaction"
                op.mark_failure()
                return "fail"

            # Withdraw operation has not gets it block yet
            # Block number may change because of the works
            op.block = int(receipt["blockNumber"], 16)

            assert op.block <= current_block
            confirmation_count = current_block - op.block

            return op.update_confirmations(confirmation_count)

    @retryable
    def get_monitored_transactions(self) -> Iterable[str]:
        """Get all transactions that are lagging behind the confirmation count."""
        result = []

        # Transactions that are broadcasted
        txs = self.dbsession.query(CryptoOperation).filter(CryptoOperation.state == CryptoOperationState.broadcasted, CryptoOperation.network_id == self.network_id)
        for tx in txs:
            result.append(bin_to_txid(tx.txid))
        return result

    def poll(self) -> Tuple[int, int]:
        """Poll geth for transaction updates.

        Get new transaction receipts for all incomplete transactions pending confirmations and try to close these operations.

        :return: tuple(how many operations got confirmed, how many internal failures we had)
        """
        return self.scan_txs()
