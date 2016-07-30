import random

import pytest
from decimal import Decimal

from eth_rpc_client import Client

from websauna.wallet.ethereum.contract import Contract
from websauna.wallet.ethereum.utils import wei_to_eth, eth_address_to_bin

from websauna.wallet.tests.eth.utils import wait_tx

# How many ETH we move for test transactiosn
TEST_VALUE = Decimal("0.01")

# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


@pytest.fixture
def tx_fee(client, geth_coinbase, hosted_wallet):
    """Estimate transaction fee."""
    # params = {"from": geth_coinbase, "to": wallet_contract_address, "value": 1}
    # response = client.make_request("eth_estimateGas", [params])
    # wei = wei_to_eth(int(response["result"], 16))
    # return wei * GAS_PRICE

    # Hardcoded for the geth test network
    return Decimal(10)


@pytest.mark.slow
def test_create_wallet(client, hosted_wallet):
    """Deploy a wallet contract on a testnet chain.

    """
    # Check we get somewhat valid ids
    assert hosted_wallet.version == 2
    assert eth_address_to_bin(hosted_wallet.address)


@pytest.mark.slow
def test_fund_wallet(client, hosted_wallet):
    """Send some funds int the wallet and see the balance updates."""

    current_balance = hosted_wallet.get_balance()

    # value = get_wallet_balance(wallet_contract_address)
    txid = send_coinbase_eth(client, TEST_VALUE, hosted_wallet.address)

    wait_tx(client, txid)

    new_balance = hosted_wallet.get_balance()

    assert new_balance == current_balance + TEST_VALUE


@pytest.mark.slow
def test_withdraw_wallet(client, topped_up_hosted_wallet, coinbase, tx_fee):
    """Withdraw eths from wallet contract to RPC coinbase address."""

    hosted_wallet = topped_up_hosted_wallet

    current_balance = hosted_wallet.get_balance()
    current_coinbase_balance = wei_to_eth(client.get_balance(coinbase))

    # We have enough coints to perform the test
    assert current_balance > TEST_VALUE

    # Withdraw and wait it go through
    txid = hosted_wallet.withdraw(coinbase, TEST_VALUE)
    wait_tx(client, txid)

    new_balance = hosted_wallet.get_balance()
    new_coinbase_balance = wei_to_eth(client.get_balance(coinbase))

    assert new_coinbase_balance != current_coinbase_balance, "Coinbase address balance did not change: {}".format(new_coinbase_balance)

    assert new_coinbase_balance > current_coinbase_balance
    assert new_balance < current_balance


@pytest.mark.slow
def test_call_contract(client: Client, topped_up_hosted_wallet, simple_test_contract: Contract):
    """Call a test contract from the hosted wallet and see the value is correctly set."""
    hosted_wallet = topped_up_hosted_wallet

    magic = random.randint(0, 2**30)
    txid = hosted_wallet.execute(simple_test_contract, "setValue", args=[magic])
    wait_tx(client, txid)

    assert simple_test_contract.value() == magic

