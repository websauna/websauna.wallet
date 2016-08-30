"""Setup initial assets and network parameters for running the demo.

"""
import gevent.monkey
gevent.monkey.patch_all()

import os
import sys

import time

import transaction
from decimal import Decimal


from websauna.system.http import Request
from websauna.system.model.retry import retryable
from websauna.wallet.ethereum.asset import get_eth_network, create_house_address, get_house_address, get_toy_box
from websauna.wallet.ethereum.confirm import finalize_pending_crypto_ops

from websauna.wallet.ethereum.service import ServiceCore
from websauna.wallet.models import AssetClass
from websauna.wallet.models import Asset
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models.heartbeat import is_network_alive, dump_network_heartbeat


def create_token(network: AssetNetwork, name: str, symbol: str, supply: int, initial_owner_address: CryptoAddress) -> Asset:
    asset = network.create_asset(name=name, symbol=symbol, supply=Decimal(supply), asset_class=AssetClass.token)
    op = initial_owner_address.create_token(asset)
    return asset


@retryable
def setup_networks(request):
    """Setup network objects.
    """

    dbsession = request.dbsession
    for network_name in ["ethereum", "testnet", "private testnet"]:
        network = get_eth_network(dbsession, network_name)
        print("Network database created ", network)


@retryable
def setup_house(request):
    """Setup different networks supported by the instance.

    Setup house wallets on each network.

    Setup ETH giveaway on testnet and private testnet.
    """

    dbsession = request.dbsession

    services = ServiceCore.parse_network_config(request)
    networks = services.keys()

    for network_name in networks:

        print("Setting up house wallet on ", network_name)

        network = get_eth_network(dbsession, network_name)
        assert is_network_alive(network), "Network was dead when we started to create address {}".format(network)

        dbsession.flush()
        house_address = get_house_address(network)

        if not house_address:
            create_house_address(network)

        if not "initial_assets" in network.other_data:
            network.other_data["initial_assets"] = {}

        if network_name == "testnet":
            network.other_data["human_friendly_name"] = "Ethereum Testnet"

        # Setup testnet ETH give away
        if network_name in ("testnet", "private testnet"):
            network.other_data["initial_assets"]["eth_amount"] = "5.0"


@retryable
def setup_toybox(request):
    """Setup TOYBOX asset for testing."""

    print("Setting up TOYBOX asset")

    dbsession = request.dbsession
    network = get_eth_network(dbsession, "testnet")
    toybox = get_toy_box(network)
    if toybox:
        return

    # Roll out toybox contract
    asset = create_token(network, "Toybox", "TOYBOX", 10222333, get_house_address(network))

    # setup toybox give away data for primary network
    network.other_data["initial_assets"]["toybox"] = str(asset.id)
    network.other_data["initial_assets"]["toybox_amount"] = 50


def ensure_networks_online(request):
    """Give time to ethereum-service process to catch up.

    Don't go forward until we have confirmed that Ethereum service is alive and talking to us.
    """
    services = ServiceCore.parse_network_config(request)
    networks = services.keys()

    while True:
        remaining_networks = []
        network_stats = []

        for network_name in networks:
            with transaction.manager:
                network = get_eth_network(request.dbsession, network_name)
                if not is_network_alive(network):
                    remaining_networks.append(network_name)
                    network_stats.append(dump_network_heartbeat(network))

        if remaining_networks:
            print("Waiting ethereum-service to wake up for networks ", network_stats)
            time.sleep(15)
            networks = remaining_networks
        else:
            break

    print("All networks green")


def bootstrap(request: Request):
    """Setup environment for demo."""
    setup_networks(request)
    ensure_networks_online(request)
    setup_house(request)
    # blocks, not so fast
    finalize_pending_crypto_ops(request.dbsession, timeout=180)
    setup_toybox(request)
    finalize_pending_crypto_ops(request.dbsession, timeout=180)


def main(argv=sys.argv):

    def usage(argv):
        cmd = os.path.basename(argv[0])
        print('usage: %s <config_uri>\n'
              '(example: "%s conf/production.ini")' % (cmd, cmd))
        sys.exit(1)

    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]

    # console_app sets up colored log output
    from websauna.system.devop.cmdline import init_websauna
    request = init_websauna(config_uri, sanity_check=True)

    bootstrap(request)
    print("Bootstrap complete")
    sys.exit(0)



