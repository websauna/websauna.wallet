"""Setup initial assets and network parameters for running the demo. """
import os
import sys
import transaction
from decimal import Decimal
from sqlalchemy.orm import Session

from websauna.system.http import Request
from websauna.system.model.retry import retryable
from websauna.wallet.ethereum.asset import get_eth_network, create_house_address, get_house_address, get_toy_box
from websauna.wallet.ethereum.confirm import finalize_pending_crypto_ops
from websauna.wallet.ethereum.ethjsonrpc import get_web3
from websauna.wallet.models import AssetClass
from websauna.wallet.models import Asset
from websauna.wallet.models import CryptoAddress
from websauna.wallet.models import AssetNetwork


def create_token(network: AssetNetwork, name: str, symbol: str, supply: int, initial_owner_address: CryptoAddress) -> Asset:
    asset = network.create_asset(name=name, symbol=symbol, supply=Decimal(supply), asset_class=AssetClass.token)
    op = initial_owner_address.create_token(asset)
    return asset


@retryable
def setup_networks(request):
    """Setup different networks supported by the instance.

    Setup house wallets on each network.

    Setup ETH giveaway on testnet and private testnet.
    """

    dbsession = request.dbsession
    for network_name in ["ethereum", "testnet", "private testnet"]:

        network = get_eth_network(dbsession, network_name)
        dbsession.flush()
        house_address = get_house_address(network)

        if not house_address:
            create_house_address(network)

        if not "initial_assets" in network.other_data:
            network.other_data["initial_assets"] = {}

        # Setup ETH give away
        if network_name in ("testnet", "private testnet"):
            network.other_data["initial_assets"]["eth_amount"] = "0.1"



@retryable
def setup_toybox(request):
    """Setup TOYBOX asset for testing."""
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


def bootstrap(request: Request):
    """Setup environment for demo."""
    setup_networks(request)
    finalize_pending_crypto_ops(request.dbsession)
    setup_toybox(request)
    finalize_pending_crypto_ops(request.dbsession)


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



