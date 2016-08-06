"""Start/stop Ethereum service."""
import os
import subprocess
import sys
from io import BytesIO

import pexpect
import time


def test_start_service(test_config_path, dbsession):
    """We can spawn a standalone Ethereum service."""

    # dbsession creates database

    log = BytesIO()
    child = pexpect.spawn('ethereum-service {}'.format(test_config_path), logfile=log)
    try:
        child.expect("Ethereum service started", timeout=10)
    except pexpect.exceptions.ExceptionPexpect:
        print(log.getvalue().decode("utf-8"))
        raise
    finally:
        child.terminate()


def test_bootstrap(test_config_path, dbsession):
    """See that our boostrap script completes."""

    log = BytesIO()
    cmdline = 'ethereum-service {}'.format(test_config_path)
    service = subprocess.Popen(cmdline, shell=True, stdout=sys.stdout, stderr=sys.stderr)

    # Takes some time to wake up, so that network heart beat is up
    time.sleep(10)
    service.poll()
    assert service.returncode == None

    bootstrap = pexpect.spawn('wallet-bootstrap {}'.format(test_config_path), logfile=log)

    try:
        # It will need to mine several blocks
        bootstrap.expect("Bootstrap complete", timeout=120)
    except Exception:
        print(log.getvalue().decode("utf-8"))
        raise
    finally:
        service.terminate()
        # Let it die gracefully before we tear down database
        time.sleep(10)
        try:
            service.kill()
        except:
            pass
