"""Test Ethereum model operations."""

import pytest
import transaction
import mock
from decimal import Decimal

import sqlalchemy

from websauna.system.user.models import User
from websauna.tests.utils import create_user
from websauna.wallet.ethereum.asset import setup_user_account
from websauna.wallet.ethereum.utils import eth_address_to_bin, txid_to_bin, bin_to_txid
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState, AssetClass
from websauna.wallet.models.blockchain import MultipleAssetAccountsPerAddress, UserCryptoOperation, UserCryptoAddress
from websauna.wallet.models.heartbeat import update_heart_beat, is_network_alive

TEST_ADDRESS = "0x2f70d3d26829e412a602e83fe8eebf80255aeea5"

TEST_TXID = "0x00df829c5a142f1fccd7d8216c5785ac562ff41e2dcfdf5785ac562ff41e2dcf"


def test_heart_beat(dbsession, eth_network_id, eth_service):
    """Create Ethereum account on Ethereum node."""

    update_heart_beat(dbsession, eth_network_id, 555)

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        assert is_network_alive(network)