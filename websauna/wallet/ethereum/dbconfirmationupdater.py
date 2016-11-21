import logging

from typing import Iterable, Tuple, Union

from sqlalchemy.orm import Session
from web3 import Web3
from websauna.system.model.retry import retryable, ensure_transactionless

from websauna.wallet.ethereum.populusutils import get_rpc_client
from websauna.wallet.ethereum.utils import txid_to_bin, bin_to_txid, bin_to_eth_address
from websauna.wallet.events import CryptoOperationCompleted
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import CryptoAddressWithdraw
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

        ensure_transactionless(transaction_manager=self.tm)

        # Don't repeat update for the same block
        with self.tm:
            network = self.dbsession.query(AssetNetwork).get(self.network_id)
            last_block = network.other_data.get("last_database_confirmation_updater_block")

        if current_block == last_block:
            logger.debug("No new blocks, still on %d, skipping confirmation updater", current_block)
            return 0, 0

        ensure_transactionless(transaction_manager=self.tm)

        txs = list(self.get_monitored_transactions())
        logger.debug("Block %d, updating confirmations for %d transactions", current_block, len(txs))

        ensure_transactionless(transaction_manager=self.tm)

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

        ensure_transactionless(transaction_manager=self.tm)

        return updates, failures

    def check_bad_hosted_wallet_events(self, op: CryptoOperation, receipt: dict):

        bad_events = {

            # OutOfGasWithdraw
            "0xb41c321524c6519973481dcf28a48b2c632cc3a7a2bb4ee1b849d68392f044e0": "Out of gas when performing the transaction. Please specify higher gas limit and try again.",

            # ExceededWithdraw
            "0x77c51a30b87b909c33ea71d8a231c335e73c443c891c73b0b2f9226dc65ffe9c": "Exceeded the available balance",

            # NoMatchingFunction
            "0x1b021189060cad216b135fb489585944f25904395c4ec6fe7d76187f32e3303d": "No matching function",
        }

        # Any of HostedWallet failure events
        # {'transactionIndex': 0, 'contractAddress': None, 'from': '0xaab2a08c0e0d8fa965e0b5167bbc33c145d29416', 'to': '0x50fd35249be4ce4e48f9f97ca8e73dba93c4f45b', 'transactionHash': '0x5b36e438f548a19ed6cdb655965fc51d67a890641a7b227b9366dc0b8d3d6f89', 'logs': [{'address': '0x50fd35249be4ce4e48f9f97ca8e73dba93c4f45b', 'transactionIndex': 0, 'logIndex': 0, 'topics': ['0xb41c321524c6519973481dcf28a48b2c632cc3a7a2bb4ee1b849d68392f044e0'], 'data': '0x000000000000000000000000f77c795e79a02a39100ac0c3f027943c60a588e70000000000000000000000000000000000000000000000000011c37937e08000', 'transactionHash': '0x5b36e438f548a19ed6cdb655965fc51d67a890641a7b227b9366dc0b8d3d6f89', 'blockHash': '0xc6ae4fe252cea45493564ffc60bfc4227af3d32615da29a2df5a503cd150487b', 'blockNumber': 9}], 'blockHash': '0xc6ae4fe252cea45493564ffc60bfc4227af3d32615da29a2df5a503cd150487b', 'cumulativeGasUsed': 34136, 'gasUsed': 34136, 'root': '5edc07ef145e2eaa489bf7cfaccff1f72548fc54b44859889b96b1be2b534141', 'blockNumber': 9}
        if isinstance(op, CryptoAddressWithdraw):
            for log in receipt["logs"]:
                # Make sure event was generated by HostedWallet, not a contract it's calling
                if log["address"] == bin_to_eth_address(op.get_from_address()):
                    for t in log["topics"]:
                        if t in bad_events:
                            return bad_events[t]

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
                op.mark_failed("Smart contract rejected the transaction")
                failures += 1
                continue

            failure_reason = self.check_bad_hosted_wallet_events(op, receipt)
            if failure_reason:
                op.mark_failed(failure_reason)
                failures += 1
                continue

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
