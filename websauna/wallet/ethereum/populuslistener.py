"""Listen smart contract events (logs, topics) for a given Populus Contract class."""

import logging
from binascii import b2a_hex
from typing import Callable, Iterable, Tuple
from ethereum import utils as ethereum_utils

from web3 import Web3

from .contractlistener import ContractListener, callback_type

#: Default logger
_logger = logging.getLogger(__name__)


#: Call on a new event. This is contract_address, event_name, translated_event_data, log_entry. Callback should return true if the event resulted any kind of update on the data structures - this is used for testing purposes.
POPULUS_CONTRACT_EVENT_CALLBACK_TYPE = Callable[[str, str, dict, dict], bool]


def create_populus_listener(web3: Web3,
                           callback: POPULUS_CONTRACT_EVENT_CALLBACK_TYPE,
                           contract: type,
                           from_block=0) -> ContractListener:
    """Create a wallet contract listener.

    Listen all events we declare in our wallet contract ABI.
    """

    events = get_contract_events(contract)

    # Parsed hex string -> event mappings.
    # We parse to avoid padding zero issues.
    event_map = {signature:event for signature, event in events}

    def _wrapper_callback(contract_address: str, signature: str, log_entry: dict):
        event = event_map.get(int(signature, 16))
        assert event, "Signature {} not in event map {}".format(signature, event_map)
        log_data = event.get_log_data(log_entry, indexed=True)
        return callback(contract_address, event.name, log_data, log_entry)

    listener = ContractListener(web3, _wrapper_callback, from_block)
    return listener


def get_event_signature(abi_data: dict):
    """Get function signature of event as Solidity handles it.
    :return:
    """

    input_types = [i["type"] for i in abi_data["inputs"]]

    signature = "{name}({arg_types})".format(
        name=abi_data["name"],
        arg_types=','.join(input_types),
    )

    return signature


def get_contract_events(contract: type) -> Iterable[Tuple[bytes, object]]:
    """Get list of events provided by Populus contract.

    :yield: events in (event topic signature as int, Event object) tuples
    """

    for member in contract.abi:
        if member["type"] == "event":
            signature = get_event_signature(member)
            hash = ethereum_utils.big_endian_to_int(ethereum_utils.sha3(signature)[:4])
            yield (hash, member["name"])

