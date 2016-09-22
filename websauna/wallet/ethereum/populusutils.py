"""Populus-related helper functions."""
import json
from typing import List, Tuple, Iterable

import gevent
from eth_client_utils import JSONRPCBaseClient

from eth_rpc_client import Client
from web3 import Web3
from web3.contract import Contract
from web3.utils.transactions import wait_for_transaction_receipt as _wait_for_transaction_receipt


class LegacyClient(JSONRPCBaseClient):
    def __init__(self, web3: Web3, *args, **kwargs):
        self.web3 = web3
        super(LegacyClient, self).__init__(*args, **kwargs)

    def make_request(self, method, params):
        data = self.web3.currentProvider.make_request(method, params)
        return json.loads(data.decode("utf-8"))


def find_abi(contract: type, signature: bytes) -> object:
    """Check if contract class implements an ABI method of a certain type.

    Ethereum contract function signature is 4 bytes.
    """

    # http://stackoverflow.com/a/34452/315168
    methods = [getattr(contract, method) for method in dir(contract) if callable(getattr(contract, method))]

    for m in methods:
        # Only Contract proxy functions have abi_signature set
        if getattr(m, "encoded_abi_signature", None) == signature:
            return m

    return None


def get_rpc_client(web3: Web3) -> Client:
    """Get Ethereum RPC client with old API for an underyling web3 client."""
    c = LegacyClient(web3)
    return c


def get_contract_address_from_txn(web3, txn_hash, timeout=120):
    txn_receipt = wait_for_transaction_receipt(web3, txn_hash, timeout)
    return txn_receipt['contractAddress']


def wait_for_transaction_receipt(web3, txn_hash, timeout=120):
    try:
        return _wait_for_transaction_receipt(web3, txn_hash, timeout)
    except gevent.Timeout as e:
        rpc = web3._requestManager.provider
        raise RuntimeError("Transaction wait timeout: {}:{}".format(rpc.host, rpc.port)) from e