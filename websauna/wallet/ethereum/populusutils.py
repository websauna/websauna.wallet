"""Populus-related helper functions."""
from typing import List, Tuple, Iterable

from eth_rpc_client import Client
from web3 import Web3
from web3.contract import Contract


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
    """Get a raw Ethereum RPC client for an underyling web3 client."""

    c = Client(web3.currentProvider.host, web3.currentProvider.port)
    c.session = web3.currentProvider.session
    return c





