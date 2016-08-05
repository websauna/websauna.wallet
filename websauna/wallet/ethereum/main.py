"""Run Ethereum operations service as a standalone daemon.

This daemon reads/writes ops from the database and broadcast them to the network via geth. It also listens to geth for incoming network events (smart contract logs).
"""

import os
import sys
import time
import logging
import transaction


from websauna.system.devop.cmdline import init_websauna
from websauna.wallet.ethereum.asset import get_eth_network
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client, get_web3
from websauna.wallet.ethereum.service import EthereumService, run_services

logger = logging.getLogger(__name__)


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri>\n'
          '(example: "%s conf/production.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):

    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]

    # console_app sets up colored log output
    request = init_websauna(config_uri, sanity_check=True)

    while True:
        run_services(request)
        time.sleep(1)

    sys.exit(0)

