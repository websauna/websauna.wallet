import pytest
from decimal import Decimal

from shareregistry.utils import txid_to_bin, eth_address_to_bin
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.wallet import create_wallet, send_coinbase_eth, get_wallet_balance, withdraw_from_wallet


# How many ETH we move for test transactiosn
from websauna.wallet.tests.integration.utils import wait_tx

TEST_VALUE = Decimal("0.0001")

# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


@pytest.mark.slow
def test_create_wallet(client):
    """Deploy a wallet contract on a testnet chain.

    """
    contract_address, txid, version = create_wallet(client)

    print("Deployed wallet {}".format(contract_address))

    # Check we get somewhat valid ids
    assert txid_to_bin(txid)
    assert version == 2
    assert eth_address_to_bin(contract_address)


@pytest.mark.slow
def test_fund_wallet(client, wallet_contract_address):
    """Send some funds int the wallet and see the balance updates."""

    current_balance = get_wallet_balance(client, wallet_contract_address)

    # value = get_wallet_balance(wallet_contract_address)
    txid = send_coinbase_eth(client, TEST_VALUE, wallet_contract_address)

    wait_tx(client, txid)

    new_balance = get_wallet_balance(client, wallet_contract_address)

    assert new_balance == current_balance + TEST_VALUE


@pytest.mark.slow
def test_withdraw_wallet(client, wallet_contract_address):
    """Withdraw eths from wallet contract to RPC coinbase address."""

    coinbase_address = client.get_coinbase()

    # Top up the wallet so we have something to withdraw
    txid = send_coinbase_eth(client, TEST_VALUE*Decimal(2), wallet_contract_address)
    wait_tx(client, txid)

    current_balance = get_wallet_balance(client, wallet_contract_address)
    current_coinbase_balance = get_wallet_balance(client, coinbase_address)

    assert current_balance > TEST_VALUE

    txid = withdraw_from_wallet(client, wallet_contract_address, coinbase_address, TEST_VALUE)

    wait_tx(client, txid)

    new_balance = get_wallet_balance(client, wallet_contract_address)
    new_coinbase_balance = get_wallet_balance(client, coinbase_address)

    assert new_coinbase_balance != current_coinbase_balance, "Coinbase address balance did not change: {}".format(new_coinbase_balance)

    assert new_coinbase_balance == current_coinbase_balance + TEST_VALUE - WITHDRAWAL_FEE
    assert new_balance == current_balance - TEST_VALUE




