import os
from uuid import UUID

import pytest
import transaction
from decimal import Decimal

from eth_rpc_client import Client

from populus.geth import create_geth_account
from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import bin_to_eth_address, to_wei, eth_address_to_bin
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState, CryptoAddressDeposit
from websauna.wallet.models.account import AssetClass
from websauna.wallet.tests.eth.utils import wait_tx

TEST_VALUE = Decimal("0.01")


@pytest.fixture
def eth_service(client, eth_network_id, dbsession, registry):
    s = EthereumService(client, eth_network_id, dbsession, registry)
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
def withdraw_address(client: Client, dbsession, eth_service: EthereumService, coinbase, deposit_address) -> str:
    """Create a managed hosted wallet that has withdraw balance for testing."""

    # Do a transaction over ETH network
    txid = client.send_transaction(_from=coinbase, to=deposit_address, value=to_wei(TEST_VALUE, ))
    wait_tx(client, txid)

    assert client.get_balance(deposit_address) > 0

    success_op_count, failed_op_count = eth_service.run_listener_operations()
    assert success_op_count == 1
    assert failed_op_count == 0

    with transaction.manager:
        # We bypass normal transction confirmation count mechanism to credit the account right away to speed up the test
        deposit = dbsession.query(CryptoAddressDeposit).one()
        deposit.resolve()

        return deposit_address


@pytest.fixture
def target_account(client: Client) -> str:
    """Create external, non-database Ethereum account, that can be used as a withdrawal target.

    :return: 0x address of the account
    """

    data_dir = os.getcwd()
    account = create_geth_account(data_dir)
    return account


@pytest.fixture(scope="module")
def token_asset(client, dbsession, eth_network_id, deploy_address, eth_service: EthereumService) -> UUID:
    """Database asset referring to the token contract.

    :return: Creation operation uuid
    """

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = network.create_asset(name="MyToken", symbol="MY", supply=10000, asset_class=AssetClass.token)
        address = CryptoAddress.get_network_address(network, eth_address_to_bin(deploy_address))
        op = address.create_token(asset)
        opid = op.id

    # This gives op a txid
    eth_service.run_waiting_operations()

    with transaction.manager:
        op = dbsession.query(CryptoOperation).get(opid)
        wait_tx(client, op.txid)
        return op.asset.id



