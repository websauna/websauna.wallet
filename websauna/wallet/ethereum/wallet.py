"""Wallet contract deployment and state management.

Deploy a wallet contract over JSON RPC using a Solidity source code as base. The wallet contract code is based on https://github.com/ethereum/meteor-dapp-wallet It features multisig where multiple authors can be required to confirm the transaction if it's above daily spend limit.

Many of these functions are cherry picked from Populous project and made Python 3 compatible.
"""
from typing import Tuple, Optional
from decimal import Decimal
import binascii

from web3.contract import Contract

from websauna.wallet.ethereum.compiler import get_compiled_contract_cached
from websauna.wallet.ethereum.contractwrapper import ContractWrapper
from websauna.wallet.ethereum.populuslistener import get_contract_events
from websauna.wallet.ethereum.utils import to_wei, wei_to_eth, ensure_0x_prefixed_hex


class HostedWallet(ContractWrapper):
    """Hosted wallet functionality.

    Calls underlying wallet contract for wallet actions taken on the behalf of the user.
    """

    @classmethod
    def abi_factory(cls, contract_name=None):
        contract_name = contract_name or "Wallet2"
        contract_meta = get_compiled_contract_cached(contract_name)
        return contract_meta

    def withdraw(self, to_address: str, amount_in_eth: Decimal, from_account=None, max_gas=0, data=None) -> str:
        """Withdraw funds from a wallet contract.

        :param amount_in_eth: How much as ETH
        :param to_address: Destination address we are withdrawing to
        :param from_account: Which Geth account pays the gas
        :return: Transaction hash as 0x string
        """

        assert isinstance(amount_in_eth, Decimal)  # Don't let floats slip through

        wei = to_wei(amount_in_eth)

        if not from_account:
            # Default to coinbase for transaction fees
            from_account = self.contract.web3.eth.coinbase

        tx_info = {
            # The Ethereum account that pays the gas for this operation
            "from": from_account,
        }

        if max_gas:
            tx_info["gas"] = max_gas
        else:
            max_gas = 0

        # Sanity check that we own this wallet
        owner = self.contract.call().owner()

        # TODO: parent ABI not stable
        owner = ensure_0x_prefixed_hex(owner)

        assert owner == from_account

        if data:
            txid = self.contract.transact(tx_info).execute(to_address, wei, max_gas, data)
        else:
            # Interact with underlying wrapped contract
            txid = self.contract.transact(tx_info).withdraw(to_address, wei, max_gas)

        return txid

    def execute(self, to_contract: Contract,
            func: str,
            args=None,
            amount_in_eth: Optional[Decimal]=None,
            max_gas=300000):
        """Calls a smart contract from the hosted wallet.

        Creates a transaction that is proxyed through hosted wallet execute method. We need to have ABI as Populus Contract instance.

        :param wallet_address: Wallet address
        :param contract: Contract to called as address bound Populus Contract class
        :param func: Method name to be called
        :param args: Arguments passed to the method
        :param value: Additional value carried in the call in ETH
        :param gas: The max amount of gas the coinbase account is allowed to pay for this transaction.
        :return: txid of the execution as hex string
        """

        assert isinstance(to_contract, Contract)

        if amount_in_eth:
            assert isinstance(amount_in_eth, Decimal)  # Don't let floats slip through
            value = to_wei(amount_in_eth)
        else:
            value = 0

        # Encode function arguments
        # function_abi = to_contract._find_matching_fn_abi(func, args)
        # 4 byte function hash
        # function_selector = function_abi_to_4byte_selector(function_abi)

        # data payload passed to the function
        arg_data = to_contract.encodeABI(func, args=args)
        call_data = arg_data  # Latest web3 behavior, no manual function selector needed

        # test_event_execute() call data should look like
        # function selector + random int as 256-bit
        # 0x5093dc7d000000000000000000000000000000000000000000000000000000002a3f58fe

        # web3 takes bytes argument as actual bytes, not hex
        call_data = binascii.unhexlify(call_data[2:])

        tx_info = {
            # The Ethereum account that pays the gas for this operation
            "from": self.contract.web3.eth.coinbase,
            "gas": max_gas,
        }

        txid = self.contract.transact(tx_info).execute(to_contract.address, value, max_gas, call_data)
        return txid

    def claim_fees(self, original_txid: str) -> Tuple[str, Decimal]:
        """Claim fees from previous execute() call.

        When a hosted wallet calls another contract through execute() gas is spent. This gas appears as cumulative gas in the transaction receipt. This gas cost should be targeted to the hosted wallet balance, not the original caller balance (geth coinbase).

        We use this method to settle the fee transaction between the hosted wallet and coinbase. This creates another event that is easy to pick up accounting and properly credit.

        :return: The new transaction id that settles the fees.
        """

        assert original_txid.startswith("0x")

        original_txid_b = bytes(bytearray.fromhex(original_txid[2:]))

        receipt = self.web3.eth.getTransactionReceipt(original_txid)
        gas_price = self.web3.eth.gasPrice

        gas_used = receipt["cumulativeGasUsed"]
        wei_value = gas_used * gas_price

        price = wei_to_eth(wei_value)

        # TODO: Estimate the gas usage of this transaction for claiming the fees
        # and add it on the top of the original transaction gas

        # Transfer value back to owner, post a tx fee event
        txid = self.contract.transact().claimFees(original_txid_b, wei_value)
        return txid, price



