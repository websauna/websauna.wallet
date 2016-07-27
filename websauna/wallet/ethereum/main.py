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
from websauna.wallet.ethereum.ethjsonrpc import get_eth_json_rpc_client
from websauna.wallet.ethereum.service import EthereumService


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

    client = get_eth_json_rpc_client(request.registry)
    with transaction.manager:
        network = get_eth_network(request.dbsession)
        network_id = network.id

    sleepy = int(request.registry.settings.get("ethereum.daemon_poll_seconds", 2))

    service = EthereumService(client, network_id, request.dbsession, request.registry)
    logger.info("Ethereum service started")
    while True:
        service.run_event_cycle()
        logger.info("Service event cycled")
        time.sleep(sleepy)

    sys.exit(0)

