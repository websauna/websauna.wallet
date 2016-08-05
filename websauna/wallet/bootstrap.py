"""
Setup initial parameters for running the demo.
"""
import transaction

from websauna.system.http import Request
from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.ethjsonrpc import get_web3
from websauna.wallet.tests.eth.utils import create_token_asset


def setup_networks(request):
    with transaction.manager:
        ethereum = get_eth_network("ethereum")
        testnet  = get_eth_network("testnet")
        assert ethereum
        assert testnet


def setup_toybox(request, eth_service, network):

    aid = create_token_asset(request.dbsession, eth_service, eth_network_id, "Toybox", "TOY", Decimal(10000))

    with transaction.manager:

        toybox = dbsession.query(Asset).get(aid)
        assert toybox.external_id

        # setup toybox give away data for primary network
        network = dbsession.query(AssetNetwork).get(eth_network_id)
        network.other_data["initial_assets"] = {}
        network.other_data["initial_assets"]["toybox"] = str(aid)
        network.other_data["initial_assets"]["toybox_amount"] = 10


def bootstrap(request: Request):
    """Setup environment for demo.

    - Give 0 ETH on main net

    - Give 5 ETH on testnet

    - Give 10 TOYBOY on testnet
    """

    web3 = get_web3(request.registry)

    # Create Toybox if we don't have one on TESTNET
    with transaction.manager:
        network = get_eth_network(request.dbsession, "testnet")
        toybox = setup_toybox(network)
