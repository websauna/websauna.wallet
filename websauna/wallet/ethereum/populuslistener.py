"""Listen smart contract events (logs, topics) for a given Populus Contract class."""

import logging
from binascii import b2a_hex
from typing import Callable

from websauna.wallet.ethereum.ethjsonrpc import EthJsonRpc
from websauna.wallet.ethereum.populusutils import get_contract_events
from .contractlistener import ContractListener, callback_type

#: Default logger
_logger = logging.getLogger(__name__)


#: Call on a new event. This is contract_address, event_name, translated_event_data, log_entry. Callback should return true if the event resulted any kind of update on the data structures - this is used for testing purposes.
POPULUS_CONTRACT_EVENT_CALLBACK_TYPE = Callable[[str, str, dict, dict], bool]


def create_populus_listener(eth_json_rpc: EthJsonRpc,
                           callback: POPULUS_CONTRACT_EVENT_CALLBACK_TYPE,
                           contract: type,
                           from_block=0) -> ContractListener:
    """Create a wallet contract listener.

    Listen all events we declare in our wallet contract ABI.
    """

    events = get_contract_events(contract)

    # Parsed hex string -> event mappings.
    # We parse to avoid padding zero issues.
    event_map = {int(signature, 16):event for signature, event in events}

    def _wrapper_callback(contract_address: str, signature: str, log_entry: dict):
        event = event_map.get(int(signature, 16))
        assert event, "Signature {} not in event map {}".format(signature, event_map)
        log_data = event.get_log_data(log_entry, indexed=True)
        return callback(contract_address, event.name, log_data, log_entry)

    listener = ContractListener(eth_json_rpc, _wrapper_callback, from_block)
    return listener

