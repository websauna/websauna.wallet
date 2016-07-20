"""Test wallet contract events. """
import random
from typing import Tuple

import pytest
from decimal import Decimal

from eth_rpc_client import Client

from populus.contracts.core import ContractBase
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.utils import to_wei
from websauna.wallet.ethereum.wallet import send_coinbase_eth

# How many ETH we move for test transactiosn
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.tests.integration.utils import wait_tx, deploy_wallet

TEST_VALUE = Decimal("0.0001")

# These values are specific to Populus private test network
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


def create_contract_listener(client: Client, contract: ContractBase) -> Tuple[ContractListener, list]:
    """Get a listener which pushes incoming events to a list object."""
    contract_events = []

    def cb(wallet_contract_address, event_name, event_data, log_entry):
        contract_events.append((event_name, event_data))
        return True  # increase updates with 1

    current_block = client.get_block_number()

    listener = create_populus_listener(client, cb, contract.__class__, from_block=current_block)
    listener.monitor_contract(contract._meta.address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    listener.poll()
    contract_events[:] = []

    return listener, contract_events


@pytest.mark.slow
def test_event_fund_wallet(client, hosted_wallet):
    """Send some funds int the wallet and see that we get the event of the deposit."""

    listener, events = create_contract_listener(client, hosted_wallet.wallet_contract)

    # value = get_wallet_balance(testnet_wallet_contract_address)
    txid = send_coinbase_eth(client, TEST_VALUE, hosted_wallet.address)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)

    # Deposit some more, should generate one new event
    txid = send_coinbase_eth(client, TEST_VALUE, hosted_wallet.address)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 2
    event_name, input_data = events[1]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)


@pytest.mark.slow
def test_event_withdraw_wallet(client: Client, topped_up_hosted_wallet, coinbase):
    """Withdraw funds from the wallet and see that we get the event of the deposit."""

    hosted_wallet = topped_up_hosted_wallet
    coinbase_address = coinbase

    listener, events = create_contract_listener(client, hosted_wallet.wallet_contract)

    txid = hosted_wallet.withdraw(coinbase_address, TEST_VALUE)
    wait_tx(client, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Withdraw"
    assert input_data["value"] == to_wei(TEST_VALUE)
    import pdb ; pdb.set_trace()
    assert input_data["spentGas"] == 100000000000000  # Hardcoded value for private test geth
    assert input_data["success"] == True
    assert input_data["to"].decode("utf-8") == coinbase_address

    # Deposit some more, should generate one new event
    txid = hosted_wallet.withdraw(coinbase_address, TEST_VALUE)
    wait_tx(client, txid)

    update_count = listener.poll()
    assert update_count == 1
    assert event_name == "Withdraw"
    assert input_data["value"] == to_wei(TEST_VALUE)
    assert input_data["spentGas"] == 100000000000000  # Hardcoded value for private test geth
    assert input_data["success"] == True
    assert input_data["to"].decode("utf-8") == coinbase_address


@pytest.mark.slow
def test_event_withdraw_wallet_too_much(client: Client, topped_up_hosted_wallet, coinbase):
    """Try to withdraw more than the wallet has."""

    hosted_wallet = topped_up_hosted_wallet
    coinbase_address = coinbase

    listener, events = create_contract_listener(client, hosted_wallet.wallet_contract)

    too_much = Decimal(99999999)

    txid = hosted_wallet.withdraw_from_wallet(coinbase_address, too_much)
    wait_tx(client, txid)

    update_count = listener.poll()

    # XXX:
    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "ExceededWithdraw"
    assert input_data["value"] == to_wei(too_much)


@pytest.mark.fail
@pytest.mark.slow
def test_event_withdraw_wallet_no_gas(client: Client, coinbase):
    """We don't have enough balance to pay the gas."""
    pass


def test_contract_abi(client, simple_test_contract):
    """Check that we can manipulate test contract from coinbase address."""

    # First check we can manipulate wallet from the coinbase address
    txid = simple_test_contract.setValue(1)
    wait_tx(client, txid)

    assert simple_test_contract.value() == 1


def test_event_execute(client: Client, topped_up_hosted_wallet, simple_test_contract):
    """Test calling a contract froma hosted wallet."""

    hosted_wallet = topped_up_hosted_wallet

    # Events of the hosted wallet
    listener, events = create_contract_listener(client, hosted_wallet.wallet_contract)

    # Events of the contract we are calling
    target_listener, target_events = create_contract_listener(client, simple_test_contract._meta.address, simple_test_contract)

    # Make gas a huge number so we don't run out of gas.
    # No idea of actual gas consumption.
    gas_amount = 300000000000000

    magic = random.randint(0, 2**30)
    txid = hosted_wallet.execute(simple_test_contract, "setValue", args=[magic], gas=gas_amount)
    wait_tx(client, txid)

    # Check events from the wallet
    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Execute"
    assert input_data["value"] == 0
    # Hmm looks like this network doesn't spend any gas
    # assert input_data["spentGas"] == 100000000000000  # Hardcoded value for private test geth
    assert input_data["to"].decode("utf-8") == simple_test_contract._meta.address

    # Check events from the testcontract.sol
    update_count = target_listener.poll()
    assert update_count == 1
    assert len(target_events) == 1
    event_name, input_data = target_events[0]
    assert event_name == "Received"
