"""Wallet contract deployment and state management.

Deploy a wallet contract over JSON RPC using a Solidity source code as base. The wallet contract code is based on https://github.com/ethereum/meteor-dapp-wallet It features multisig where multiple authors can be required to confirm the transaction if it's above daily spend limit.

Many of these functions are cherry picked from Populous project and made Python 3 compatible.
"""
import os
from typing import Tuple, Iterable, Optional

from decimal import Decimal

from eth_rpc_client import Client

from populus.contracts import Contract, deploy_contract
from populus.contracts.core import ContractBase
from populus.utils import get_contract_address_from_txn

from websauna.wallet.ethereum.populuscontract import get_compiled_contract_cached
from websauna.wallet.ethereum.utils import to_wei, wei_to_eth


#: Gas limits are at
#: https://github.com/ethereum/meteor-dapp-wallet#gas-usage-statistics
#: but they are only guidelining, not accurate anymore
DEFAULT_WALLET_CREATION_GAS = 2500400  # 1919430 gas, 0.0383886 Ether ($0.40)


#: Wallet contract ABI and such
_contract = None


class WalletCreationError(Exception):
    """Wallet contract could not be deployed. Most likely out of gas."""


def get_wallet_contract_class() -> type:
    name = "Wallet"
    contract_meta = get_compiled_contract_cached("simplewallet.sol", name)
    contract = Contract(contract_meta, name)
    return contract


def send_coinbase_eth(rpc: Client, amount: Decimal, address: str) -> str:
    """Draw some funds from the wallet coinbase account and send them to a (contract) address.

    :param amount: Send value in ethers
    :return: transaction id
    """

    wei = to_wei(amount)
    coinbase = rpc.get_coinbase()
    txid = rpc.send_transaction(_from=coinbase, to=address, value=wei)
    return txid


class HostedWallet:
    """Hosted wallet functionality.

    Calls underlying wallet contract for wallet actions taken on the behalf of the user.
    """

    def __init__(self, wallet_contract: ContractBase, version=0, initial_txid=None):
        """
        :param wallet_contract: Populus Contract object for underlying wallet contract
        :param version: What is the version of the deployed contract.
        :param initial_txid: Set on wallet creation to the txid that deployed the contract. Only available objects accessed through create().
        """

        # Make sure we are bound to an address
        assert wallet_contract._meta.address
        self.wallet_contract = wallet_contract

        self.version = version

        self.initial_txid = initial_txid

    @property
    def address(self) -> str:
        """Get wallet address as 0x hex string."""
        return self.wallet_contract._meta.address

    @property
    def client(self) -> Client:
        """Get access to RPC client we are using for this wallet."""
        return self.wallet_contract._meta.blockchain_client

    def get_balance(self) -> Decimal:
        """Gets the balance on this contract address over RPC and converts to ETH."""
        return wei_to_eth(self.wallet_contract.get_balance())

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

    def execute(self, contract: ContractBase,
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

    @classmethod
    def get(cls, rpc: Client, address: str, contract=get_wallet_contract_class()) -> "HostedWallet":
        """Get a proxy object to existing hosted wallet contrac.t"""

        assert address.startswith("0x")
        instance = contract(address, rpc)
        return HostedWallet(instance, rpc)


    @classmethod
    def create(cls, rpc: Client, wait_for_tx_seconds=90, gas=DEFAULT_WALLET_CREATION_GAS, contract=get_wallet_contract_class()) -> ContractBase:
        """Creates a new hosted wallet.

        The cost of deployment is paid from coinbase account.

        :param contract: Which contract we deploy as Populus Contract class.

        :return: Populus Contract proxy object for new contract
        """
        version = 2  # Hardcoded for now

        txid = deploy_contract(rpc, contract, gas=gas)

        if wait_for_tx_seconds:
            rpc.wait_for_transaction(txid, max_wait=wait_for_tx_seconds)
        else:
            # We cannot get contract address until the block is mined
            return (None, txid, version)

        try:
            contract_addr = get_contract_address_from_txn(rpc, txid)
        except ValueError:
            raise WalletCreationError("Could not create wallet with {} gas. Txid {}. Out of gas? Check in http://testnet.etherscan.io/tx/{}".format(DEFAULT_WALLET_CREATION_GAS, txid, txid))

        instance = contract(contract_addr, rpc)
        return HostedWallet(instance, version=2, initial_txid=txid)



