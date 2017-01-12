"""Integration test fixtures."""
from decimal import Decimal

import pytest
import transaction
from websauna.system.user.models import User
from websauna.tests.utils import create_user

from websauna.wallet.ethereum.asset import get_ether_asset, setup_user_account
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.service import EthereumService


from websauna.wallet.models import AssetNetwork, CryptoAddress, Asset, UserCryptoAddress
from websauna.wallet.tests.eth.utils import mock_create_addresses


@pytest.fixture
def eth_json_rpc(registry):
    """Create Ethereum RPC connection for integration tests."""
    return get_eth_json_rpc_client(registry)


@pytest.fixture
def eth_service(web3, eth_network_id, dbsession, registry):
    """Create Ethereum Service to run ops or mock ups."""
    s = EthereumService(web3, eth_network_id, dbsession, registry)
    return s


@pytest.fixture
def mock_eth_service(eth_network_id, dbsession, registry):
    """Non-functional Ethereum Service without a connection to geth."""

    from web3 import RPCProvider, Web3
    web3 = Web3(RPCProvider("127.0.0.1", 666))
    s = EthereumService(web3, eth_network_id, dbsession, registry)
    return s


@pytest.fixture
def testnet_service(web3, testnet_network_id, dbsession, registry):
    """Create Ethereum Service for testnet to run ops or mock ups."""
    s = EthereumService(web3, testnet_network_id, dbsession, registry)
    return s


@pytest.fixture
def eth_faux_address(dbsession, registry, eth_network_id):
    """Create a faux address that is not registered on node."""
    with transaction.manager:
        address = CryptoAddress(network_id=eth_network_id)
        address.address = "xxx"
    return address.address


@pytest.fixture()
def user_id(dbsession, registry):
    """Create a sample user."""
    with transaction.manager:
        user = create_user(dbsession, registry)
        return user.id


@pytest.fixture()
def topped_up_user(dbsession, registry, mock_eth_service, user_id, eth_network_id, eth_asset_id):
    """User has some ETH on their account."""
    with transaction.manager:
        user = dbsession.query(User).get(user_id)
        setup_user_account(user, do_mainnet=True)

    mock_create_addresses(mock_eth_service, dbsession)

    with transaction.manager:
        user = dbsession.query(User).first()
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        asset = dbsession.query(Asset).get(eth_asset_id)
        address = UserCryptoAddress.get_default(user, network)
        account = address.address.get_or_create_account(asset)
        account.account.do_withdraw_or_deposit(Decimal("+10"), "Top up")



