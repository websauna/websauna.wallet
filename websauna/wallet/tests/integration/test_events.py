"""Test wallet contract events. """
from typing import Tuple

import binascii
import pytest
from decimal import Decimal

from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.ethjsonrpc import EthJsonRpc
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.ethereum.wallet import send_coinbase_eth, get_wallet_contract_class

# How many ETH we move for test transactiosn
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.tests.integration.utils import wait_tx

TEST_VALUE = Decimal("0.0001")

# These values are specific to Populus private test network
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


def create_contract_listener(client: EthJsonRpc, wallet_contract_address) -> Tuple[ContractListener, list]:
    """Get a listener which pushes incoming events to a list object."""
    contract_events = []

    def cb(wallet_contract_address, event_name, event_data, log_entry):
        contract_events.append((event_name, event_data))
        return True  # increase updates with 1

    current_block = client.get_block_number()

    listener = create_populus_listener(client, cb, get_wallet_contract_class(), from_block=current_block)
    listener.monitor_contract(wallet_contract_address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    listener.poll()
    contract_events[:] = []

    return listener, contract_events


@pytest.mark.slow
def test_event_fund_wallet(client, wallet_contract_address):
    """Send some funds int the wallet and see that we get the event of the deposit."""

    listener, events = create_contract_listener(client, wallet_contract_address)

    # value = get_wallet_balance(testnet_wallet_contract_address)
    txid = send_coinbase_eth(client, TEST_VALUE, wallet_contract_address)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)

    # Deposit some more, should generate one new event
    txid = send_coinbase_eth(client, TEST_VALUE, wallet_contract_address)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 2
    event_name, input_data = events[1]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)

