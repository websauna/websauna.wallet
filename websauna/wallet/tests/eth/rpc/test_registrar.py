import random

import pytest
from decimal import Decimal

from web3 import Web3
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached

from websauna.wallet.ethereum.contract import Contract, confirm_transaction, deploy_contract
from websauna.wallet.ethereum.utils import wei_to_eth, eth_address_to_bin

from websauna.wallet.tests.eth.utils import wait_tx, send_balance_to_contract

# How many ETH we move for test transactiosn
TEST_VALUE = Decimal("0.01")


@pytest.mark.slow
def xxx_test_registrar_wallet(web3: Web3):
    """Create registrar contract and register a wallet against it."""

    # Check we get somewhat valid ids
    contract_def = get_compiled_contract_cached("OwnedRegistrar")
    registrar_contract, txid = deploy_contract(web3, contract_def)

    # Deploy wallet main contract
    contract_def = get_compiled_contract_cached("Wallet")
    wallet_contract, txid = deploy_contract(web3, contract_def)

    # Register wallet
    registrar_contract.transact().setAddr("wallet", wallet_contract.address)

    # Deploy ProxyWallet against the registered wallet
    contract_def = get_compiled_contract_cached("Relay")
    relay, txid = deploy_contract(web3, contract_def, constructor_arguments=[registrar_contract.address, "wallet"])




@pytest.mark.slow
def xxx_test_upgrade_wallet(web3: Web3):
