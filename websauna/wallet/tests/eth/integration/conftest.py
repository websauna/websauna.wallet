import os
from uuid import UUID

import pytest
import transaction
from decimal import Decimal

from geth.wrapper import DEFAULT_PASSWORD_PATH
from web3 import Web3
from eth_rpc_client import Client

from geth.accounts import create_new_account

from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import bin_to_eth_address, to_wei, eth_address_to_bin, bin_to_txid
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState, CryptoAddressDeposit
from websauna.wallet.models.account import AssetClass
from websauna.wallet.tests.eth.utils import wait_tx, wait_for_op_confirmations, send_balance_to_address

TEST_VALUE = Decimal("0.01")


@pytest.fixture
def eth_service(web3, eth_network_id, dbsession, registry):
    s = EthereumService(web3, eth_network_id, dbsession, registry)
    register_eth_operations(registry)
    return s


@pytest.fixture
def deposit_address(eth_service, eth_network_id, dbsession, registry) -> str:
    """Creates an address that has matching account on Geth.

    Sending ETH to this address should trigger a incoming tx logic.

    :return: 0x hex presentation
    """

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)

        address = CryptoAddress(network=network)

        dbsession.flush()

        # Generate address on the account
        op = CryptoAddressCreation(address)
        dbsession.add(op)
        dbsession.flush()

    # Creates a hosted wallet
    success_op_count, failed_op_count = eth_service.run_waiting_operations()
    assert success_op_count == 1

    with transaction.manager:
        return bin_to_eth_address(dbsession.query(CryptoAddress).one().address)


@pytest.fixture
def withdraw_address(web3: Web3, dbsession, eth_service: EthereumService, coinbase, deposit_address) -> str:
    """Create a managed hosted wallet that has withdraw balance for testing."""

    # Do a transaction over ETH network
    txid = send_balance_to_address(web3, deposit_address, TEST_VALUE)
    confirm_transaction(web3, txid)

    assert web3.eth.getBalance(deposit_address) > 0

    success_op_count, failed_op_count = eth_service.run_listener_operations()
    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        # We bypass normal transction confirmation count mechanism to credit the account right away to speed up the test
        deposit = dbsession.query(CryptoAddressDeposit).one()
        deposit.resolve()

        return deposit_address


@pytest.fixture
def target_account(web3: Web3) -> str:
    """Create a new Ethereum account on a running Geth node.

    The account can be used as a withdrawal target for tests.

    :return: 0x address of the account
    """

    # We store keystore files in the current working directory
    # of the test run
    data_dir = os.getcwd()

    # Use the default password "this-is-not-a-secure-password"
    # as supplied in geth/default_blockchain_password file.
    # The supplied password must be bytes, not string,
    # as we only want ASCII characters and do not want to
    # deal encoding problems with passwords
    account = create_new_account(data_dir, DEFAULT_PASSWORD_PATH)
    return account


@pytest.fixture
def token_asset(client, dbsession, eth_network_id, deposit_address, eth_service: EthereumService) -> UUID:
    """Database asset referring to the token contract.

    deposit_address will hold 10000 tokens

    :return: Asset id
    """

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = network.create_asset(name="MyToken", symbol="MY", supply=Decimal(10000), asset_class=AssetClass.token)
        address = CryptoAddress.get_network_address(network, eth_address_to_bin(deposit_address))
        op = address.create_token(asset)
        opid = op.id
        aid = asset.id

    # This gives op a txid
    success, fails = eth_service.run_waiting_operations()
    assert success == 1

    wait_for_op_confirmations(eth_service, opid)

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = dbsession.query(Asset).get(aid)
        address = CryptoAddress.get_network_address(network, eth_address_to_bin(deposit_address))
        account = address.get_account(asset)
        assert account.account.get_balance() > 0
        return aid



