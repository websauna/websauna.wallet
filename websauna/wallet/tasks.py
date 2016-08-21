"""Celery tasks."""
import logging

import time

import redis_lock
from celery import Task
from websauna.system.core.redis import get_redis
from websauna.system.task import task
from websauna.wallet.ethereum.service import ServiceCore, OneShot

logger = logging.getLogger(__name__)


@task(name="update_networks", bind=True)
def update_networks(self: Task):
    """Update all incoming and outgoing events from a network."""

    request = self.request.request
    redis = get_redis(request)

    # Get list of configured networks
    services = ServiceCore.parse_network_config(request)

    for network_name in services.keys():
        # Update each network separately and have a lock to ensure we don't
        # accidentally do two overlapping update runs
        # https://pypi.python.org/pypi/python-redis-lock
        lock = redis_lock.Lock(redis, "network-update-lock-{}".format(network_name))

        if not lock.acquire(blocking=False):
            # This network is still procesing pending operations from the previous task run
            logger.warn("Could not acquire lock on %s when doing update_networks", network_name)
            continue

        lock.release()

        with lock:
            logger.info("Updating network %s", network_name)
            start = time.time()
            one_shot = OneShot(request, network_name, services[network_name])
            one_shot.run_shot()
            logger.info("Updated network %s in %d seconds", network_name, time.time() - start)