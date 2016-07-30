import random

import pytest
from decimal import Decimal

from web3 import Web3

from websauna.wallet.ethereum.contract import Contract
from websauna.wallet.ethereum.utils import wei_to_eth, eth_address_to_bin

from websauna.wallet.tests.eth.utils import wait_tx, send_balance_to_contract

# How many ETH we move for test transactiosn
TEST_VALUE = Decimal("0.01")


@pytest.mark.slow
def test_create_wallet(hosted_wallet):
    """Deploy a wallet contract on a testnet chain.

    """
    # Check we get somewhat valid ids
    assert hosted_wallet.version == 2
    assert eth_address_to_bin(hosted_wallet.address)


@pytest.mark.slow
def test_fund_wallet(web3, coinbase, hosted_wallet):
    """Send some funds int the wallet and see the balance updates."""

    current_balance = wei_to_eth(web3.eth.getBalance(hosted_wallet.address))

    # value = get_wallet_balance(wallet_contract_address)
    txid = send_balance_to_contract(hosted_wallet, TEST_VALUE)

    wait_tx(web3, txid)

    new_balance = hosted_wallet.get_balance()

    assert new_balance == current_balance + TEST_VALUE


@pytest.mark.slow
def test_withdraw_wallet(web3, topped_up_hosted_wallet, coinbase):
    """Withdraw eths from wallet contract to RPC coinbase address."""

    hosted_wallet = topped_up_hosted_wallet

    current_balance = hosted_wallet.get_balance()
    current_coinbase_balance = wei_to_eth(web3.eth.getBalance(coinbase))

    # We have enough coints to perform the test
    assert current_balance > TEST_VALUE

    # Withdraw and wait it go through
    txid = hosted_wallet.withdraw(coinbase, TEST_VALUE)
    wait_tx(web3, txid)

    new_balance = hosted_wallet.get_balance()
    new_coinbase_balance = wei_to_eth(web3.eth.getBalance(coinbase))

    assert new_coinbase_balance != current_coinbase_balance, "Coinbase address balance did not change: {}".format(new_coinbase_balance)

    assert new_coinbase_balance > current_coinbase_balance
    assert new_balance < current_balance


@pytest.mark.slow
def test_call_contract(web3: Web3, topped_up_hosted_wallet, simple_test_contract: Contract):
    """Call a test contract from the hosted wallet and see the value is correctly set."""
    hosted_wallet = topped_up_hosted_wallet

    magic = random.randint(0, 2**30)
    txid = hosted_wallet.execute(simple_test_contract, "setValue", args=[magic])
    wait_tx(web3, txid)

    assert simple_test_contract.value() == magic

