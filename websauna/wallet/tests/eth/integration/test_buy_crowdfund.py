"""Test buying into crowdfund contract."""
from typing import Callable
from uuid import UUID

import pytest
import time
import transaction
from decimal import Decimal

from populus.utils.wait import wait_for_block_number
from web3 import Web3
from web3.utils.currency import to_wei


from sqlalchemy.orm import Session

from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid, wei_to_eth, bin_to_eth_address
from websauna.wallet.ethereum.wallet import HostedWallet
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw
from websauna.wallet.models import CryptoOperationState
from websauna.wallet.models import CryptoOperationType
from websauna.wallet.models.account import AssetClass
from websauna.wallet.ethereum.token import Token


def get_crowdsale_data(token: Token) -> dict:
    """Capture real-time data from network."""
    name = token.contract.call().name()
    symbol = token.contract.call().symbol()
    supply = Decimal(token.contract.call().totalSupply())
    wei_cap = token.contract.call().weiCap()
    wei_raised = token.contract.call().weiRaised()
    investor_count = token.contract.call().investorCount()
    price_divider = token.contract.call().priceDivider()
    price_multiplier = token.contract.call().priceMultiplier()
    return locals()


@pytest.fixture
def token(dbsession, web3, eth_service, eth_network_id) -> Callable:
    # signer, multisig, cap
    extra_arguments = [
        web3.eth.coinbase,
        "0x8f480474b014ea63d4fe5e52478e833fb9e8f938",  # Mikko's testnet address
        to_wei(6000, "ether"),
        2,  # 2 share per each ETH
        10**18,  # 1 ETH 10**18 wei
    ]

    token = Token.create_token(web3, name="Toycrowd", supply=0, symbol="TOYCROWD", owner=web3.eth.coinbase, extra_arguments=extra_arguments, contract_name="CrowdfundToken")

    print("Token deployed")

    return token


def get_wallet(web3, address):
    return HostedWallet.get(web3, address)


@pytest.fixture
def toycrowd(dbsession, web3, eth_service, eth_network_id, token) -> Callable:
    """Set up a Toycrowd asset.

    :return: Crowdsale callable
    """

    data = get_crowdsale_data(token)

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = network.create_asset(name=data["name"], symbol=data["symbol"], supply=data["supply"], asset_class=AssetClass.token)
        bin_address = eth_address_to_bin(token.address)
        asset.external_id = bin_address
        asset.other_data["contract"] = "CrowdfundToken"
        dbsession.add(asset)
        dbsession.flush()
        asset_id = asset.id

    return lambda: dbsession.query(Asset).get(asset_id)


def test_buy_crowdfund_not_enough_gas(dbsession: Session, eth_network_id: UUID, web3: Web3, eth_service: EthereumService, token, toycrowd, withdraw_address):
    """Perform a crowdfundn buy operation without giving enough gas for the transaction."""

    with transaction.manager:

        # Create withdraw operation
        caccount = dbsession.query(CryptoAddressAccount).one()

        # Use 4 as the heurestics for block account that doesn't happen right away, but still sensible to wait for it soonish
        asset = toycrowd()

        caccount.withdraw(Decimal(0.005), asset.external_id, "Buying Toycrowd", required_confirmation_count=1)

    print("Withdrawing")

    success_op_count, failed_op_count = eth_service.run_waiting_operations()
    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 3  # Create + deposit + withdraw
        op = ops[-1]
        txid = bin_to_txid(op.txid)

    # This should make the tx to included in a block
    confirm_transaction(web3, txid)

    # This should trigger incoming notification
    eth_service.run_listener_operations()

    # Now we should get block number for the withdraw
    updates, failures = eth_service.run_confirmation_updates()
    assert failures == 1

    with transaction.manager:
        op = dbsession.query(CryptoOperation).all()[-1]
        assert op.is_failed()
        assert "gas" in op.get_failure_reason()


def test_buy_crowdfund_with_gas(dbsession: Session, eth_network_id: UUID, web3: Web3, eth_service: EthereumService, token, toycrowd, rich_withdraw_address):
    """Perform a crowdfunnd buy operation without giving enough gas for the transaction."""

    with transaction.manager:

        # Create withdraw operation
        caccount = dbsession.query(CryptoAddressAccount).one()

        # Use 4 as the heurestics for block account that doesn't happen right away, but still sensible to wait for it soonish
        asset = toycrowd()

        op = caccount.withdraw(Decimal(3), asset.external_id, "Buying Toycrowd", required_confirmation_count=1)
        op.other_data["gas"] = 2500333  # Limit should be ~100k

    success_op_count, failed_op_count = eth_service.run_waiting_operations()
    assert failed_op_count == 0
    assert success_op_count == 1

    with transaction.manager:
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 3  # Create + deposit + withdraw
        op = ops[-1]
        txid = bin_to_txid(op.txid)

    # This should make the tx to included in a block
    confirm_transaction(web3, txid)

    # Set op.block
    eth_service.run_confirmation_updates()

    # Grab block number where out tx is
    with transaction.manager:
        ops = list(dbsession.query(CryptoOperation).all())
        op = ops[-1]
        block_num = op.block

    wallet = get_wallet(web3, rich_withdraw_address)
    token_events = token.get_all_events()
    wallet_events = wallet.get_all_events()

    # Confirm we got it all right
    receipt = web3.eth.getTransactionReceipt(txid)
    logs = receipt["logs"]
    assert logs[0]["topics"][0] == token_events["Buy"]
    assert logs[1]["topics"][0] == token_events["Transfer"]
    assert logs[2]["topics"][0] == wallet_events["Withdraw"]

    data = get_crowdsale_data(token)
    assert data["wei_raised"] == to_wei("3", "ether")

    # Give tx time to confirm, so all confirmations will be there for db update run
    required_conf = 3
    wait_for_block_number(web3, block_num + required_conf + 1, timeout=60)

    # This should trigger incoming notification
    eth_service.run_listener_operations()
    updates, failures = eth_service.run_confirmation_updates()
    assert failures == 0
    assert updates == 2  # 1 eth withdraw, 1 token deposit

    # Check our db is updated
    with transaction.manager:

        # There is now new operation to deposit tokens
        ops = list(dbsession.query(CryptoOperation).all())
        assert len(ops) == 4
        op = ops[-1]  # type: CryptoOperation

        assert op.operation_type == CryptoOperationType.deposit
        assert op.state == CryptoOperationState.success
        assert op.amount == 6

        asset = toycrowd()
        crypto_address = dbsession.query(CryptoAddress).one()  # type: CryptoAddress
        caccount = crypto_address.get_account(asset)
        assert caccount.account.get_balance() == 6