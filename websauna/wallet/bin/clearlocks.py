"""Clear Redis wallet locks."""
import os
from getpass import getpass

import sys

import redis_lock
from websauna.system.core.redis import get_redis
from websauna.wallet.ethereum.service import OneShot
from websauna.wallet.ethereum.service import ServiceCore


def main(argv=sys.argv):

    def usage(argv):
        cmd = os.path.basename(argv[0])
        print('usage: %s <config_uri> <network name>\n'
              '(example: "%s conf/production.ini")' % (cmd, cmd))
        sys.exit(1)

    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]

    # console_app sets up colored log output
    from websauna.system.devop.cmdline import init_websauna
    request = init_websauna(config_uri, sanity_check=True)

    # Get list of configured networks
    services = ServiceCore.parse_network_config(request)
    redis = get_redis(request)

    for network_name in services.keys():
        # Update each network separately and have a lock to ensure we don't
        # accidentally do two overlapping update runs
        # https://pypi.python.org/pypi/python-redis-lock
        lock = redis_lock.Lock(redis, "network-update-lock-{}".format(network_name))

        if not lock.acquire(blocking=False):
            # This network is still procesing pending operations from the previous task run
            print("Lock {} is blocked, reseting".format(network_name))
            lock.reset()
        else:
            lock.release()

    print("Unlock complete")
    sys.exit(0)

