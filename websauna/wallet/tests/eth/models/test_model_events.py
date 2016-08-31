"""Test we reach completed event for various operations."""

import pytest
import transaction

from websauna.wallet.events import CryptoOperationCompleted, CryptoOperationPerformed, IncomingCryptoDeposit
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState, AssetClass
from websauna.wallet.models.blockchain import MultipleAssetAccountsPerAddress, UserCryptoOperation, UserCryptoAddress, CryptoAddressDeposit
from websauna.wallet.tests.eth.mockservice import MockEthereumService
from websauna.wallet.tests.eth.utils import mock_create_addresses, TEST_ADDRESS, do_faux_deposit


@pytest.fixture
def eth_service(eth_network_id, dbsession, registry):
    # We don't run any real network facing operations, all operations are closed by tests
    s = MockEthereumService(eth_network_id, dbsession, registry)
    return s


@pytest.yield_fixture()
def captured_registry_events(registry):
    """A hack to capture registry.notify()"""

    events = []

    old_notify = registry.notify
    def notify(event):
        old_notify(event)
        events.append(event)

    registry.notify = notify

    yield events

    registry.notify = old_notify


def test_account_creation_completed(dbsession, eth_network_id, eth_service: MockEthereumService, captured_registry_events):
    """We receive completed event on account creation."""

    with transaction.manager:
        network = dbsession.query(AssetNetwork).get(eth_network_id)

        address = CryptoAddress(network=network)

        dbsession.flush()

        # Generate address on the account
        op = CryptoAddressCreation(address)
        op.required_confirmation_count = 1
        dbsession.add(op)
        dbsession.flush()

        op_id = op.id

    eth_service.run_test_ops()

    # We get performed event on
    events = captured_registry_events
    assert len(events) == 2
    assert isinstance(events[0], CryptoOperationPerformed)
    assert isinstance(events[1], CryptoOperationCompleted)


def test_deposit_completed(dbsession, eth_network_id, eth_service: MockEthereumService, eth_asset_id, topped_up_user, captured_registry_events):
    """We receive completed event on deposit."""

    with transaction.manager:
        user_address = dbsession.query(UserCryptoAddress).first()
        do_faux_deposit(user_address.address, eth_asset_id, 10)

    eth_service.run_test_ops()

    # We get performed event on
    events = captured_registry_events
    assert len(events) == 3
    assert isinstance(events[0], CryptoOperationPerformed)
    assert isinstance(events[1], IncomingCryptoDeposit)
    assert isinstance(events[2], CryptoOperationCompleted)


