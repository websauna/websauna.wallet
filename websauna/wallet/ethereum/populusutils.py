"""Populus-related helper functions."""
from typing import List, Tuple, Iterable

from populus.contracts import Function
from populus.contracts.events import Event


def find_abi(contract: type, signature: bytes) -> Function:
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


def get_contract_events(contract: type) -> Iterable[Tuple[bytes, Event]]:
    """Get list of events provided by Populus contract.

    :yield: events in (event topic signature, Event object) tuples
    """
    for attr_name in dir(contract):
        attr = getattr(contract, attr_name)
        if isinstance(attr, Event):
            yield (attr.event_topic, attr)