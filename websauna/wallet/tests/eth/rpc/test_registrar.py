import random

import pytest
from decimal import Decimal

from web3 import Web3
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached

from websauna.wallet.ethereum.contract import Contract, confirm_transaction, deploy_contract, get_contract
from websauna.wallet.ethereum.utils import wei_to_eth, eth_address_to_bin, to_wei

from websauna.wallet.tests.eth.utils import wait_tx, send_balance_to_contract

# How many ETH we move for test transactiosn
TEST_VALUE = Decimal("0.01")


def decode_addr(addr):
    return "0x" + addr.decode("ascii")


@pytest.mark.slow
def test_registrar_based_wallet(web3: Web3, coinbase):
    """Create registrar contract and register a wallet against it."""

    wei_amount = to_wei(TEST_VALUE)

    # Check we get somewhat valid ids
    contract_def = get_compiled_contract_cached("OwnedRegistrar")
    registrar_contract, txid = deploy_contract(web3, contract_def)

    # Deploy wallet contract body
    contract_def = get_compiled_contract_cached("Wallet")
    wallet_contract, txid = deploy_contract(web3, contract_def)

    # Register wallet contract body
    assert wallet_contract.address
    txid = registrar_contract.transact().setAddr(b"wallet", wallet_contract.address)
    confirm_transaction(web3, txid)

    import pdb ; pdb.set_trace()

    # Check registration succeeded
    assert decode_addr(registrar_contract.call().addr(b"wallet")) == wallet_contract.address

    # Wallet implementation says we are 1.0
    assert wallet_contract.call().version().decode("utf-8") == "1.0"

    # Deploy relay against the registered wallet
    contract_def = get_compiled_contract_cached("Relay")
    assert registrar_contract.address
    relay, txid = deploy_contract(web3, contract_def, constructor_arguments=[registrar_contract.address, "wallet"])

    # Test relayed wallet. We use Wallet ABI
    # against Relay contract.
    contract_def = get_compiled_contract_cached("Wallet")
    relayed_wallet = get_contract(web3, contract_def, relay.address)

    # Check relay internal data structures
    assert decode_addr(relay.call().registrarAddr()) == registrar_contract.address
    assert relay.call().name().decode("ascii") == "wallet"

    # We point to the wallet implementation
    impl_addr = decode_addr(relay.call().getImplAddr())
    assert impl_addr == wallet_contract.address

    # Read static field
    impl_wallet = get_contract(web3, contract_def, impl_addr)
    assert impl_wallet.call().version().decode("utf-8") == "1.0"

    # Deposit some ETH
    txid = send_balance_to_contract(relayed_wallet.address, wei_amount)
    confirm_transaction(web3, txid)
    assert relayed_wallet.web3.eth.getBalance(relayed_wallet.address, wei_amount)

    # Withdraw ETH back
    relayed_wallet.transact().withdraw(coinbase, wei_amount)
    confirm_transaction(web3, txid)
    assert relayed_wallet.web3.eth.getBalance(relayed_wallet.address, 0)


@pytest.mark.slow
def xxx_test_upgrade_wallet(web3: Web3):

    # Check we get somewhat valid ids
    contract_def = get_compiled_contract_cached("OwnedRegistrar")
    registrar_contract, txid = deploy_contract(web3, contract_def)

    # Deploy wallet contract body
    contract_def = get_compiled_contract_cached("Wallet")
    wallet_contract, txid = deploy_contract(web3, contract_def)

    # Register wallet contract body
    txid = registrar_contract.transact().setAddr("wallet", wallet_contract.address)
    confirm_transaction(web3, txid)

    # Deploy relay against the registered wallet
    contract_def = get_compiled_contract_cached("Relay")
    relay, txid = deploy_contract(web3, contract_def, constructor_arguments=[registrar_contract.address, "wallet"])

    # Test relayed wallet. We use Wallet ABI
    # against Relay contract.
    contract_def = get_compiled_contract_cached("Wallet")
    relayed_wallet = get_contract(web3, contract_def, relay.address)
    assert relayed_wallet.call().version() == "1.0"

    #
    # Upgrade wallet
    #

    # Deploy wallet contract body
    contract_def = get_compiled_contract_cached("Wallet")
    wallet_contract, txid = deploy_contract(web3, contract_def)
