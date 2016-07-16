"""Test wallet contract events. """
from typing import Tuple

import pytest
from decimal import Decimal

from shareregistry.utils import txid_to_bin, eth_address_to_bin
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.ethjsonrpc import EthJsonRpc
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.wallet import create_wallet, send_coinbase_eth, get_wallet_balance, withdraw_from_wallet, get_wallet_contract_class

# How many ETH we move for test transactiosn
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.tests.integration.utils import wait_tx

TEST_VALUE = Decimal("0.0001")

# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


@pytest.fixture
def testnet_contract_address():
    """Predeployed wallet version 2 contract in testnet with some balance."""
    return "0x9d8ad3ffc65cecb906bee4759d5422eb7c77f919"


def create_contract_listener(eth_json_rpc: EthJsonRpc, contract_address) -> Tuple[ContractListener, list]:

    contract_events = []

    def cb(contract_address, txid, data):
        contract_events.append(cb)

    current_block = eth_json_rpc.get_block_number()

    listener = create_populus_listener(eth_json_rpc, cb, get_wallet_contract_class(), from_block=current_block)
    listener.monitor_contract(contract_address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    contract_events[:] = []

    return listener, contract_events


@pytest.mark.slow
def test_event_fund_wallet(eth_json_rpc, testnet_contract_address):
    """Send some funds int the wallet and see that we get the event of the deposit."""

    listener, events = create_contract_listener(eth_json_rpc, testnet_contract_address)

    # value = get_wallet_balance(testnet_contract_address)
    txid = send_coinbase_eth(eth_json_rpc, TEST_VALUE, testnet_contract_address)
    wait_tx(eth_json_rpc, txid)
    update_count = listener.poll()

    assert update_count == 1
    assert len(events) == 1


