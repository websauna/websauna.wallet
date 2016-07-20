"""Populus contract helpers."""

#: Compiled contracts in in-process memory
import os

from websauna.wallet.ethereum.solidity import solc


_cache = {}


def _compile_solc_contract(fname, name) -> dict:
    """Get our internal wallet implementation compiled Solidity.
    :return:
    """

    contract_file = os.path.join(os.path.dirname(__file__), "sol", fname)
    assert os.path.exists(contract_file)

    sol_output = solc(input_files=[contract_file], rich=True)
    return sol_output[name]


def get_compiled_contract_cached(fname: str, name: str) -> dict:
    """Return data struct given by solc compiled."""
    key = fname + ":" + name
    _contract = _cache.get(key) or _compile_solc_contract(fname, name)
    _cache[key] = _contract
    return _contract