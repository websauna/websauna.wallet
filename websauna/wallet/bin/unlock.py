"""Simple script to unlock coinbase account."""
import os
from getpass import getpass

import sys

from websauna.wallet.ethereum.service import OneShot
from websauna.wallet.ethereum.service import ServiceCore


def main(argv=sys.argv):

    def usage(argv):
        cmd = os.path.basename(argv[0])
        print('usage: %s <config_uri> <network name>\n'
              '(example: "%s conf/production.ini testnet")' % (cmd, cmd))
        sys.exit(1)

    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]
    network_name = argv[2]

    # console_app sets up colored log output
    from websauna.system.devop.cmdline import init_websauna
    request = init_websauna(config_uri, sanity_check=True)

    services = ServiceCore.parse_network_config(request)
    one_shot = OneShot(request, network_name, services[network_name], require_unlock=False)
    one_shot.setup()

    coinbase = one_shot.web3.eth.coinbase

    pw = getpass("Give password to unlock {} on {}:".format(coinbase, network_name))

    one_shot.web3.personal.unlockAccount(coinbase, pw, 30*24*3600)

    print("Unlock complete")
    sys.exit(0)

