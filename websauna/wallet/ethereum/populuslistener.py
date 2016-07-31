"""Listen smart contract events (logs, topics) for a given Populus Contract class."""

import logging
from binascii import b2a_hex
from typing import Callable, Iterable, Tuple
from ethereum import utils as ethereum_utils

from web3 import Web3

from .contractlistener import ContractListener, callback_type
from .decodeutils import decode_multi
from .decodeutils import decode_single


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


def get_contract_events(contract: type) -> Iterable[Tuple[bytes, object]]:
    """Get list of events provided by Populus contract.

    :yield: events in (event topic signature as int, Event object) tuples
    """

    for member in contract.abi:
        if member["type"] == "event":
            event = Event(member["name"], member["inputs"], member["anonymous"])
            hash = event.event_topic
            hash = int(hash, 16)
            yield (hash, event)


class EmptyDataError(Exception):
    pass


class Event:
    """Helper class for managing topics/events.

    Lifted from Populus 0.8.0 before web3 migration.
    """

    def __init__(self, name, inputs, anonymous):
        self.name = name
        self.inputs = inputs
        self.anonymous = anonymous

    @property
    def event_topic(self):
        return hex(ethereum_utils.big_endian_to_int(
            ethereum_utils.sha3(self.signature)
        )).strip('L')

    @property
    def signature(self):
        signature = "{name}({arg_types})".format(
            name=self.name,
            arg_types=','.join(self.input_types),
        )
        return signature

    @property
    def input_types(self):
        """
        Iterable of the types this function takes.
        """
        if self.inputs:
            return [i['type'] for i in self.inputs]
        return []

    @property
    def outputs(self):
        return [input for input in self.inputs if not input['indexed']]

    @property
    def output_types(self):
        """
        Iterable of the types this function takes.
        """
        if self.outputs:
            return [i['type'] for i in self.outputs]

        return []

    def cast_return_data(self, outputs, raw=False):
        if raw or len(self.output_types) != 1:
            try:
                return decode_multi(self.output_types, outputs)
            except AssertionError:
                raise EmptyDataError("call to {0} unexpectedly returned no data".format(self))
        output_type = self.output_types[0]

        try:
            return decode_single(output_type, outputs)
        except AssertionError:
            raise EmptyDataError("call to {0} unexpectedly returned no data".format(self))

    def get_log_data(self, log_entry, indexed=False):
        values = self.cast_return_data(log_entry['data'], raw=True)
        event_data = {
            output['name']: value for output, value in zip(self.outputs, values)
        }
        if indexed:
            for idx, _input in enumerate(self.inputs):
                if _input['indexed']:
                    event_data[_input['name']] = decode_single(
                        _input['type'],
                        log_entry['topics'][idx + 1],
                    )
        return event_data