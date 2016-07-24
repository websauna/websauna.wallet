import pytest
import transaction

from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService
from websauna.wallet.ethereum.utils import bin_to_eth_address
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import AssetNetwork, CryptoAddressCreation, CryptoOperation, CryptoAddress, Asset, CryptoAddressAccount, CryptoAddressWithdraw, CryptoOperationState


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

