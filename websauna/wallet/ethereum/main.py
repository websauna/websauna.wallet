"""Run Ethereum operations service as a standalone daemon.

This daemon reads/writes ops from the database and broadcast them to the network via geth. It also listens to geth for incoming network events (smart contract logs).
"""

import os
import sys
import time
import logging


from websauna.system.devop.cmdline import init_websauna
from websauna.wallet.ethereum.service import run_services, one_shot

logger = logging.getLogger(__name__)


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
    request = init_websauna(config_uri, sanity_check=True)

    run_services(request)
    sys.exit(0)


def one_shot_main(argv=sys.argv):
    """Run one debug cycle"""

    def usage(argv):
        cmd = os.path.basename(argv[0])
        print('usage: %s <config_uri> <network name>\n'
              '(example: "%s conf/production.ini") ethereum' % (cmd, cmd))
        sys.exit(1)

    if len(argv) < 3:
        usage(argv)

    config_uri = argv[1]
    network_name = argv[2]

    # console_app sets up colored log output
    request = init_websauna(config_uri, sanity_check=True)
    one_shot(request, network_name)

    sys.exit(0)
