"""Wallet contract deployment and state management.

Deploy a wallet contract over JSON RPC using a Solidity source code as base. The wallet contract code is based on https://github.com/ethereum/meteor-dapp-wallet It features multisig where multiple authors can be required to confirm the transaction if it's above daily spend limit.

Many of these functions are cherry picked from Populous project and made Python 3 compatible.
"""
from typing import Tuple, Optional

from decimal import Decimal

from websauna.wallet.ethereum.contract import Contract
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached
from websauna.wallet.ethereum.contractwrapper import ContractWrapper
from websauna.wallet.ethereum.utils import to_wei, wei_to_eth


class HostedWallet(ContractWrapper):
    """Hosted wallet functionality.

    Calls underlying wallet contract for wallet actions taken on the behalf of the user.
    """

    @classmethod
    def abi_factory(cls):
        name = "Wallet"
        contract_meta = get_compiled_contract_cached(name)
        return contract_meta

    def withdraw(self, to_address: str, amount_in_eth: Decimal):
        """Withdraw funds from a wallet contract.

        :param amount_in_eth: How much
        :param to_address: Address we are withdrawing to
        :return: Transaction id
        """

        assert isinstance(amount_in_eth, Decimal)  # Don't let floats slip through

        wei = to_wei(amount_in_eth)
        txid = self.wallet_contract.withdraw(to_address, wei)
        return txid

    def execute(self, contract: Contract,
            method: str,
            args=[],
            amount_in_eth: Optional[Decimal]=None,
            gas=100000):
        """Calls a smart contract from the hosted wallet.

        Creates a transaction that is proxyed through hosted wallet execute method. We need to have ABI as Populus Contract instance.

        :param wallet_address: Wallet address
        :param contract: Contract to called as address bound Populus Contract class
        :param method: Method name to be called
        :param args: Arguments passed to the method
        :param value: Additional value carried in the call in ETH
        :param gas: The max amount of gas the hosted wallet is allowed to pay for this call
        :return: txid of the execution as hex string
        """
        if amount_in_eth:
            assert isinstance(amount_in_eth, Decimal)  # Don't let floats slip through
            value = to_wei(amount_in_eth)
        else:
            value = 0

        func = getattr(contract, method)

        # Encode function arguments
        data = func.get_call_data(args)
        data = bytes(bytearray.fromhex(data[2:]))

        address = contract._meta.address
        txid = self.wallet_contract.execute(address, value, gas, data)
        return txid

    def claim_fees(self, original_txid: str) -> Tuple[str, Decimal]:
        """Claim fees from previous execute() call.

        When a hosted wallet calls another contract through execute() gas is spent. This gas appears as cumulative gas in the transaction receipt. This gas cost should be targeted to the hosted wallet balance, not the original caller balance (geth coinbase).

        We use this method to settle the fee transaction between the hosted wallet and coinbase. This creates another event that is easy to pick up accounting and properly credit.

        :return: The new transaction id that settles the fees.
        """

        assert original_txid.startswith("0x")

        original_txid_b = bytes(bytearray.fromhex(original_txid[2:]))

        receipt = self.client.get_transaction_receipt(original_txid)
        gas_price = self.client.get_gas_price()

        gas_used = int(receipt["cumulativeGasUsed"], 16)
        wei_value = gas_used * gas_price

        price = wei_to_eth(wei_value)

        # TODO: Estimate the gas usage of this transaction for claiming the fees
        # and add it on the top of the original transaction gas

        # Transfer value back to owner, post a tx fee event
        txid = self.wallet_contract.claimFees(original_txid_b, wei_value)
        return txid, price




