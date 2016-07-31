"""Test wallet contract events. """
import random

import pytest
from decimal import Decimal

from eth_rpc_client import Client

from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.ethereum.utils import to_wei, txid_to_bin

# How many ETH we move for test transactiosn
from websauna.wallet.tests.eth.utils import wait_tx, create_contract_listener, send_balance_to_contract

TEST_VALUE = Decimal("0.0001")

# These values are specific to Populus private test network
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


@pytest.mark.slow
def test_event_fund_wallet(web3, hosted_wallet):
    """Send some funds int the wallet and see that we get the event of the deposit."""

    listener, events = create_contract_listener(hosted_wallet.contract)

    # value = get_wallet_balance(testnet_wallet_contract_address)
    txid = send_balance_to_contract(hosted_wallet, TEST_VALUE)
    confirm_transaction(web3, txid)

    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Deposit"
    assert input_data["value"] == to_wei(TEST_VALUE)

    # Deposit some more, should generate one new event
    txid = send_balance_to_contract(hosted_wallet, TEST_VALUE)
    confirm_transaction(web3, txid)

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

    listener, events = create_contract_listener(hosted_wallet.wallet_contract)

    # Do a withdraw from wallet
    txid = hosted_wallet.withdraw(coinbase_address, TEST_VALUE)
    wait_tx(client, txid)

    # Wallet contract should generate events if the withdraw succeeded or not
    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1
    event_name, input_data = events[0]
    assert event_name == "Withdraw"
    assert input_data["value"] == to_wei(TEST_VALUE)
    assert input_data["to"].decode("utf-8") == coinbase_address

    # Deposit some more, should generate one new event
    txid = hosted_wallet.withdraw(coinbase_address, TEST_VALUE)
    wait_tx(client, txid)

    update_count = listener.poll()
    assert update_count == 1
    assert event_name == "Withdraw"
    assert input_data["value"] == to_wei(TEST_VALUE)
    assert input_data["to"].decode("utf-8") == coinbase_address


@pytest.mark.slow
def test_event_withdraw_wallet_too_much(client: Client, topped_up_hosted_wallet, coinbase):
    """Try to withdraw more than the wallet has."""

    hosted_wallet = topped_up_hosted_wallet
    coinbase_address = coinbase

    listener, events = create_contract_listener(hosted_wallet.wallet_contract)

    too_much = Decimal(99999999)

    txid = hosted_wallet.withdraw(coinbase_address, too_much)
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
    listener, events = create_contract_listener(hosted_wallet.wallet_contract)

    # Events of the contract we are calling
    target_listener, target_events = create_contract_listener(simple_test_contract)

    # Make gas a huge number so we don't run out of gas.
    # No idea of actual gas consumption.
    gas_amount = 400000000000000

    balance_before = hosted_wallet.get_balance()

    magic = random.randint(0, 2**30)
    txid = hosted_wallet.execute(simple_test_contract, "setValue", args=[magic], gas=gas_amount)
    wait_tx(client, txid)

    balance_after = hosted_wallet.get_balance()

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

    # Doing call() doesn't incur any gas cost on the contract
    assert balance_after == balance_before

    # Check events from the testcontract.sol
    update_count = target_listener.poll()
    assert update_count == 1
    assert len(target_events) == 1
    event_name, input_data = target_events[0]
    assert event_name == "Received"


def test_event_claim_fees(client, topped_up_hosted_wallet, coinbase):
    """We correctly can claim transaction fees from the hosted wallet contract."""

    hosted_wallet = topped_up_hosted_wallet
    coinbase_address = coinbase

    listener, events = create_contract_listener(hosted_wallet.wallet_contract)

    assert hosted_wallet.get_balance() > TEST_VALUE

    txid = hosted_wallet.withdraw(coinbase_address, TEST_VALUE)
    wait_tx(client, txid)

    claim_txid, price = hosted_wallet.claim_fees(txid)
    wait_tx(client, claim_txid)

    update_count = listener.poll()
    assert update_count == 2
    assert len(events) == 2
    event_name, input_data = events[-1]  # Fee claim event

    assert event_name == "ClaimFee"
    assert input_data["txid"] == txid_to_bin(txid)  # This was correctly targeted to original withdraw
    assert input_data["value"] == to_wei(price)  # We claimed correct amount

