"""Celery tasks."""
import datetime
import logging
import os
import threading
import time

import redis_lock
from celery import Task
from websauna.system.core.redis import get_redis
from websauna.system.task.tasks import task, WebsaunaTask
from websauna.system.task.tasks import RetryableTransactionTask
from websauna.wallet.ethereum.service import ServiceCore, OneShot
from websauna.wallet.events import NetworkStats, ServiceUpdated
from websauna.wallet.models import AssetNetwork
from websauna.wallet.models.heartbeat import dump_network_heartbeat

logger = logging.getLogger(__name__)


BAD_LOCK_TIMEOUT = 3600


@task(name="blockchain.update_networks", bind=True, time_limit=60*30, soft_time_limit=60*15, base=WebsaunaTask)
def update_networks(self: Task):
    """Update all incoming and outgoing events from a network through Celery.

    Offer an alternative for runnign standalone ethereum-service.
    """

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

            lock_acquired_at = redis.get("network-update-lock-started-{}".format(network_name))
            lock_acquired_by = redis.get("network-update-lock-started-by-{}".format(network_name))

            if lock_acquired_by:
                lock_acquired_by = lock_acquired_by.decode("utf-8")

            if lock_acquired_at:
                try:
                    friendly_at = datetime.datetime.utcfromtimestamp(lock_acquired_at)
                except:
                    friendly_at = 0

                diff = time.time() - float(lock_acquired_at)
                if diff > BAD_LOCK_TIMEOUT:
                    logger.warn("Failed to get wallet update lock on %s network when doing update_networks for %f seconds, originally acquired by %s at %s", network_name, diff, friendly_at, lock_acquired_by)

            continue

        lock.release()

        with lock:
            redis.set("network-update-lock-started-{}".format(network_name), time.time())
            redis.set("network-update-lock-started-by-{}".format(network_name), "process: {} thread:{}".format(os.getpid(), threading.current_thread()))

            logger.info("Updating network %s", network_name)
            start = time.time()
            one_shot = OneShot(request, network_name, services[network_name])
            one_shot.run_shot()
            logger.info("Updated network %s in %d seconds", network_name, time.time() - start)

            redis.delete("network-update-lock-started-{}".format(network_name))
            redis.delete("network-update-lock-started-by-{}".format(network_name))

            request.registry.notify(ServiceUpdated(request, network_name, time.time() - start))


@task(name="blockchain.post_network_stats", bind=True, time_limit=60*30, soft_time_limit=60*15, base=RetryableTransactionTask)
def post_network_stats(self: Task):
    request = self.request.request
    dbsession = request.dbsession
    services = ServiceCore.parse_network_config(request)
    for network in dbsession.query(AssetNetwork).all():
        if network.name in services.keys():
            stats = dump_network_heartbeat(network)
            request.registry.notify(NetworkStats(request, network.name, stats))

