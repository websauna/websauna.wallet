import pytest
from decimal import Decimal

from shareregistry.utils import txid_to_bin, eth_address_to_bin
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.wallet import create_wallet, send_coinbase_eth, get_wallet_balance, withdraw_from_wallet


@pytest.fixture
def testnet_contract_address():
    """Predeployed wallet version 2 contract in testnet."""
    return "0xc5910bcb2442e84845aa98b20ca51e8f5d2bee23"


@pytest.mark.slow
def test_create_wallet(eth_json_rpc):
    """Deploy a wallet contract on a testnet chain.

    """
    contract_address, txid, version = create_wallet(eth_json_rpc)

    # Check we get somewhat valid ids
    assert txid_to_bin(txid)
    assert version == 2
    assert eth_address_to_bin(contract_address)


@pytest.mark.slow
def test_fund_wallet(eth_json_rpc, testnet_contract_address):
    """Send some funds int the wallet and see the balance updates."""

    current_balance = get_wallet_balance(eth_json_rpc, testnet_contract_address)

    # value = get_wallet_balance(testnet_contract_address)
    txid = send_coinbase_eth(eth_json_rpc, Decimal("0.1"), testnet_contract_address)

    eth_json_rpc.wait_for_transaction(txid, max_wait=60.0)

    new_balance = get_wallet_balance(eth_json_rpc, testnet_contract_address)

    assert new_balance == current_balance + Decimal("0.1")


@pytest.mark.slow
def test_withdraw_wallet(eth_json_rpc, testnet_contract_address):
    """Withdraw eths from wallet contract to RPC coinbase address."""

    coinbase_address = eth_json_rpc.get_coinbase()

    current_balance = get_wallet_balance(eth_json_rpc, testnet_contract_address)
    current_coinbase_balance = get_wallet_balance(eth_json_rpc, coinbase_address)

    txid = withdraw_from_wallet(eth_json_rpc, testnet_contract_address, coinbase_address, Decimal("0.1"))
    print("Sending out transaction ", txid)

    eth_json_rpc.wait_for_transaction(txid, max_wait=60.0)

    new_balance = get_wallet_balance(eth_json_rpc, testnet_contract_address)
    new_coinbase_balance = get_wallet_balance(eth_json_rpc, testnet_contract_address)

    assert new_balance == current_balance - Decimal("0.1")
    assert new_coinbase_balance == current_coinbase_balance + Decimal("0.1")



