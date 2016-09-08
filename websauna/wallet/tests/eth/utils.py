from typing import Tuple

from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

import pytest
import time
import transaction

import mock

from web3 import Web3
from web3.contract import Contract
from web3.utils.transactions import wait_for_transaction_receipt

from websauna.wallet.ethereum.asset import get_house_address
from websauna.wallet.ethereum.contractlistener import ContractListener
from websauna.wallet.ethereum.populuslistener import create_populus_listener
from websauna.wallet.ethereum.service import EthereumService


# http://testnet.etherscan.io/tx/0xe9f35838f45958f1f2ddcc24247d81ed28c4aecff3f1d431b1fe81d92db6c608
from websauna.wallet.ethereum.utils import to_wei, eth_address_to_bin, txid_to_bin, bin_to_txid
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models import Asset
from websauna.wallet.models import AssetClass
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoAddressDeposit
from websauna.wallet.models import UserCryptoAddress
from websauna.wallet.models import UserCryptoOperation

from websauna.wallet.ethereum.confirm import wait_for_op_confirmations

GAS_PRICE = Decimal("0.00000002")
GAS_USED_BY_TRANSACTION = Decimal("32996")

#: How much withdrawing from a hosted wallet costs to the wallet owner
WITHDRAWAL_FEE = GAS_PRICE * GAS_USED_BY_TRANSACTION


NETWORK_PARAMETERS = {
    "local_geth": {
        "withdrawal_fee": Decimal(0)
    },

    "testnet": {
        "withdrawal_fee": WITHDRAWAL_FEE
    }
}


TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"



def wait_tx(web3: Web3, txid: str):
    return wait_for_transaction_receipt(web3, txid, 60)


def create_contract_listener(contract: Contract) -> Tuple[ContractListener, list]:
    """Get a listener which pushes incoming events of one contract to a list object."""

    assert isinstance(contract, Contract)
    contract_events = []

    web3 = contract.web3

    def cb(wallet_contract_address, event_name, event_data, log_entry):
        contract_events.append((event_name, event_data))
        return True  # increase updates with 1

    current_block = web3.eth.blockNumber

    listener = create_populus_listener(web3, cb, contract.__class__, from_block=current_block)
    listener.monitor_contract(contract.address)

    # There might be previously run tests that wrote events in the current block
    # Let's flush them out
    listener.poll()
    contract_events[:] = []

    return listener, contract_events


def get_withdrawal_fee(web3: Web3) -> Decimal:
    """How much gas HostedWallet withdraw() operation should cost."""

    # Some broken abstraction here - assume test web3 instance
    # tells us more about the network implicitly
    mode = getattr(web3, "mode", "local_geth")
    return NETWORK_PARAMETERS[mode]["withdrawal_fee"]


def send_balance_to_contract(contract: Contract, value: Decimal) -> str:
    """Send balance from geth coinbase to the contract.

    :param contract: Contract instance with an address

    :param value: How much to send

    :return: Transaction hash of the send operation
    """
    web3 = contract.web3
    tx = {
        "from": web3.eth.coinbase,
        "to": contract.address,
        "value": to_wei(value)
    }
    return web3.eth.sendTransaction(tx)


def send_balance_to_address(web3: Web3, address: str, value: Decimal) -> str:
    assert address.startswith("0x")
    tx = {
        "from": web3.eth.coinbase,
        "to": address,
        "value": to_wei(value)
    }
    return web3.eth.sendTransaction(tx)


def create_token_asset(dbsession, eth_service, eth_network_id, name, symbol, supply, wait=True) -> UUID:
    """Create a token in the network and assigns it to coinbase address."""

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = network.create_asset(name=name, symbol=symbol, supply=Decimal(10000), asset_class=AssetClass.token)
        address = get_house_address(network)
        op = address.create_token(asset)
        opid = op.id
        aid = asset.id

    # This gives op a txid
    success, fails = eth_service.run_waiting_operations()
    assert success > 0
    assert fails == 0

    if wait:
        wait_for_op_confirmations(eth_service, opid)
    return aid


def mock_create_addresses(eth_service, dbsession, address=TEST_ADDRESS):
    """Create fake addresses instead of going to geth to ask for new address."""

    def _create_address(service, dbsession, opid):
        with transaction.manager:
            op = dbsession.query(CryptoOperation).get(opid)
            assert isinstance(op.address, CryptoAddress)
            op.address.address = eth_address_to_bin(address)
            op.mark_performed()
            op.mark_complete()

    with mock.patch("websauna.wallet.ethereum.ops.create_address", new=_create_address):
        success_op_count, failed_op_count = eth_service.run_waiting_operations()

    assert success_op_count == 1
    assert failed_op_count == 0
    return success_op_count, failed_op_count


def do_faux_deposit(address: CryptoAddress, asset_id, amount) -> CryptoAddressDeposit:
    """Simulate deposit to address."""

    network = address.network
    txid = network.other_data["test_txid_pool"].pop()
    # txid = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"
    dbsession = Session.object_session(address)
    asset = dbsession.query(Asset).get(asset_id)
    txid = txid_to_bin(txid)

    op = address.deposit(Decimal(amount), asset, txid, bin_to_txid(txid))
    op.required_confirmation_count = 1
    op.external_address = address.address
    dbsession.add(op)
    dbsession.flush()
    return op


def do_faux_withdraw(user_address: UserCryptoAddress, target_address, asset_id, amount) -> UserCryptoOperation:
    """Simulate user withdrawing assets from one of his addresses."""
    dbsession = Session.object_session(user_address)
    asset = dbsession.query(Asset).get(asset_id)
    op = user_address.withdraw(asset, Decimal(amount), eth_address_to_bin(target_address), "Simulated withraw", required_confirmation_count=1)
    return op


