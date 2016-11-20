"""Test buying into crowdfund contract."""
from typing import Callable
from uuid import UUID

import pytest
import time
import transaction
from decimal import Decimal

from web3 import Web3
from web3.utils.currency import to_wei


from sqlalchemy.orm import Session

from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid, wei_to_eth, bin_to_eth_address
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw
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
        dbsession.add(asset)
        dbsession.flush()
        asset_id = asset.id

    return lambda: dbsession.query(Asset).get(asset_id)


def test_buy_crowdfund(dbsession: Session, eth_network_id: UUID, web3: Web3, eth_service: EthereumService, token, toycrowd, withdraw_address):
    """Perform a withdraw operation.

    Create a database address with balance.
    """

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
    eth_service.run_confirmation_updates()

    data = get_crowdsale_data(token)

    assert data["wei_raised"] == 1000


