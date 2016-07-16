"""Listen smart contract events (logs, topics) and wrap them Populus Event objects when we detect them in a blockchain."""
import logging
from binascii import b2a_hex
from typing import Callable

from websauna.wallet.ethereum.ethjsonrpc import EthJsonRpc
from websauna.wallet.ethereum.populusutils import get_contract_events
from .contractlistener import ContractListener, callback_type

#: Default logger
_logger = logging.getLogger(__name__)


def create_populus_listener(eth_json_rpc: EthJsonRpc,
                           callback: Callable,
                           contract: type,
                           from_block=0) -> ContractListener:
    """Create a wallet contract listener.

    Listen all events we declare in our wallet contract ABI.
    """

    events = get_contract_events(contract)

    event_map = {signature:event for signature, event in events}

    def _wrapper_callback(contract_address: str, signature: str, log_entry: dict):
        event = event_map.get(signature)
        assert event, "Signature {} not in event map {}".format(signature, event_map)
        log_data = event.get_log_data(log_entry, indexed=True)
        import pdb ; pdb.set_trace()

    listener = ContractListener(eth_json_rpc, _wrapper_callback, from_block)
    return listener

