"""Wallet contract deployment and state management.

Deploy a wallet contract over JSON RPC using a Solidity source code as base. The wallet contract code is based on https://github.com/ethereum/meteor-dapp-wallet It features multisig where multiple authors can be required to confirm the transaction if it's above daily spend limit.

Many of these functions are cherry picked from Populous project and made Python 3 compatible.
"""
import os
from typing import Tuple, Iterable

from decimal import Decimal
from populus.contracts import Contract, deploy_contract
from populus.contracts.core import ContractBase
from populus.utils import get_contract_address_from_txn
from rlp.utils_py3 import encode_hex
from ethereum import abi

from websauna.wallet.ethereum.ethjsonrpc import EthJsonRpc
from websauna.wallet.ethereum.utils import to_wei, wei_to_eth
from .solidity import solc


#: Gas limits are at
#: https://github.com/ethereum/meteor-dapp-wallet#gas-usage-statistics
#: but they are only guidelining, not accurate anymore
DEFAULT_WALLET_CREATION_GAS = 2500400  # 1919430 gas, 0.0383886 Ether ($0.40)


#: Wallet contract ABI and such
_contract = None


class WalletCreationError(Exception):
    """Wallet contract could not be deployed. Most likely out of gas."""


def _get_wallet_contract(name) -> dict:
    """Get our internal wallet implementation compiled Solidity.
    :return:
    """

    contract_file = os.path.join(os.path.dirname(__file__), "sol", "simplewallet.sol")
    assert os.path.exists(contract_file)

    sol_output = solc(input_files=[contract_file], rich=True)
    return sol_output[name]


def _get_wallet_contract_cached(name="Wallet"):
    global _contract
    _contract = _contract or _get_wallet_contract(name)
    return _contract


def get_wallet_contract_class(name="Wallet") -> type:
    contract_meta = _get_wallet_contract_cached(name)
    contract = Contract(contract_meta, name)
    return contract


def create_wallet(rpc: EthJsonRpc, gas=DEFAULT_WALLET_CREATION_GAS, wait_for_tx_seconds=60, daily_limit=Decimal(50)) -> Tuple[str, str, int]:
    """Deploy a wallet contract on the blockchain.

    :param rpc: Ethernet client used to deploy the contract
    :param gas: Max gas limit for creating the wallet contract
    :param wait_for_tx_seconds: Wait until the block is mined (otherwise we won't get contract address)
    :param daily_limit: How much we are allowed to withdraw from the wallet per day
    :return: (Contract address, transaction id, contract version) tuple.
    """
    version = 2  # Hardcoded for now

    contract = get_wallet_contract_class()
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

    return contract_addr, txid, version


def send_coinbase_eth(rpc: EthJsonRpc, amount: Decimal, address: str) -> str:
    """Draw some funds from the wallet coinbase account and send them to a (contract) address.

    :param amount: Send value in ethers
    :return: transaction id
    """

    wei = to_wei(amount)
    coinbase = rpc.get_coinbase()
    txid = rpc.send_transaction(_from=coinbase, to=address, value=wei)
    return txid


def get_wallet_balance(rpc: EthJsonRpc, contract_address: str) -> Decimal:
    """Return the wallet contract ETH holdings.

    :return: Amount in ether
    """
    cb = get_wallet_contract_class()
    c = cb(contract_address, rpc)
    return wei_to_eth(c.get_balance())


def withdraw_from_wallet(rpc: EthJsonRpc, contract_address: str, to_address: str, amount_in_eth: Decimal, data=None) -> str:
    """Withdraw funds from a wallet contract.

    :param rpc: RPC client
    :param contract_address: Wallet contract we are withdrawing from (assume owner is RPC coinbase account)
    :param amount_in_eth: How much
    :param to_address: Address we are withdrawing to
    :return: Transaction id
    """

    cb = get_wallet_contract_class()
    c = cb(contract_address, rpc)  # type: ContractBase

    wei = to_wei(amount_in_eth)
    if not data:
        data = ""

    # multiowned.execute() called
    txid = c.execute(to_address, wei, data)
    return txid





