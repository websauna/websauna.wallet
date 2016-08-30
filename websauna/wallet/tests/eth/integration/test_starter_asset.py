"""Start/stop Ethereum service."""
import transaction
from decimal import Decimal
from web3 import Web3

from shareregistry.utils import bin_to_eth_address
from websauna.system.user.models import User
from websauna.tests.utils import create_user
from websauna.wallet.ethereum.asset import setup_user_account, get_ether_asset
from websauna.wallet.ethereum.contract import confirm_transaction
from websauna.wallet.ethereum.populusutils import get_rpc_client
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.token import Token
from websauna.wallet.models.blockchain import CryptoOperationType, UserCryptoAddress, CryptoOperationState
from websauna.wallet.tests.eth.utils import wait_for_op_confirmations
from websauna.wallet.models import CryptoOperation
from websauna.wallet.models import Asset
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import CryptoAddressDeposit
from websauna.wallet.models import AssetNetwork


def test_starter_eth(dbsession, registry, eth_network_id, web3: Web3, eth_service: EthereumService, house_address, starter_eth):
    """Test the user gets some starter ETH when signing up."""

    with transaction.manager:
        user = create_user(dbsession, registry)
        setup_user_account(user)

    # Let all the events completed
    success, fail = eth_service.run_event_cycle()
    assert success >= 1
    assert fail == 0

    # When op is confirmed, the user account is correctly credited
    with transaction.manager:
        user = dbsession.query(User).first()
        txid = user.user_data["starter_asset_txs"][0]

    confirm_transaction(web3, txid)

    # Let the transfer come through
    eth_service.run_event_cycle()

    with transaction.manager:
        user = dbsession.query(User).first()
        client = get_rpc_client(web3)
        asset = get_ether_asset(dbsession)
        ua = user.owned_crypto_addresses.first()
        address = bin_to_eth_address(ua.address.address)

        # Sanity check we get events from starter deposit
        logs = client.get_logs(from_block=0, address=[address])

        ops = list(user.owned_crypto_operations)

        # The event was processed on log level
        assert len(logs) == 1

        # The last user operation is deposit
        depo = ops[-1]
        assert isinstance(depo.crypto_operation, CryptoAddressDeposit)
        opid = depo.crypto_operation.id

    # Wait deposit to confirm
    wait_for_op_confirmations(eth_service, opid)

    with transaction.manager:
        # User ETH balance is expected
        asset = get_ether_asset(dbsession)
        user = dbsession.query(User).first()
        ua = user.owned_crypto_addresses.first()
        caccout = ua.address.get_account(asset)
        assert caccout.account.get_balance() == Decimal("0.1")


def test_starter_token(dbsession, registry, eth_network_id, web3: Web3, eth_service: EthereumService, house_address, toybox):
    """See that a fresh user account is supplied with some play assets."""

    with transaction.manager:
        user = create_user(dbsession, registry)
        setup_user_account(user)

    # Let all the events completed
    success, fail = eth_service.run_event_cycle()
    assert success == 1
    assert fail == 0

    # We need another event cycle to process the initial asset transfers
    with transaction.manager:
        user = dbsession.query(User).first()
        opid = user.user_data["starter_asset_ops"][0]

    wait_for_op_confirmations(eth_service, opid)

    # Let the transfer come through
    eth_service.run_event_cycle()

    # Make sure we confirm the deposit
    with transaction.manager:
        user = dbsession.query(User).first()
        user_depo = user.owned_crypto_operations.join(CryptoOperation).filter_by(operation_type=CryptoOperationType.deposit).first()
        opid = user_depo.crypto_operation.id

    wait_for_op_confirmations(eth_service, opid)

    with transaction.manager:

        # Sanity check our token contract posts us logs
        user = dbsession.query(User).first()
        client = get_rpc_client(web3)
        asset = dbsession.query(Asset).get(toybox)
        address = bin_to_eth_address(asset.external_id)
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        user_address = UserCryptoAddress.get_default(user, network).address
        house_address = dbsession.query(CryptoAddress).get(house_address)
        house = bin_to_eth_address(house_address.address)
        token = Token.get(web3, address)

        # Check we correctly resolved low level logs
        token_logs = client.get_logs(from_block=0, address=[address])
        wallet_logs = client.get_logs(from_block=0, address=[house])
        assert len(token_logs) > 0
        assert len(wallet_logs) > 0

        # Check contract state matches
        assert token.contract.call().balanceOf(house) == 9990
        assert token.contract.call().balanceOf(bin_to_eth_address(user_address.address)) == 10

        # Check our internal book keeping matches
        assert house_address.get_account(asset).account.get_balance() == 9990
        assert user_address.get_account(asset).account.get_balance() == 10
