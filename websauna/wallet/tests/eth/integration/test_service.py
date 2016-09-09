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
        child.expect("Ethereum service started", timeout=30)
    except pexpect.exceptions.ExceptionPexpect:
        print(log.getvalue().decode("utf-8"))
        raise
    finally:
        child.terminate()
        time.sleep(10)
        try:
            child.kill()
        except:
            pass


def test_bootstrap(test_config_path, dbsession):
    """See that our boostrap script completes."""

    log = BytesIO()
    cmdline = 'ethereum-service {}'.format(test_config_path)
    service = subprocess.Popen(cmdline, shell=True, stdout=sys.stdout, stderr=sys.stderr)

    # Takes some time to wake up, so that network heart beat is up
    time.sleep(15)
    service.poll()
    assert service.returncode == None

    bootstrap = pexpect.spawn('wallet-bootstrap {}'.format(test_config_path), logfile=log)

    # If you see  b'Fatal: Could not open database: resource temporarily unavailable'
    # then there is a dangling geth process around you need to kill by hand

    try:
        # It will need to mine several blocks
        bootstrap.expect("Bootstrap complete", timeout=600)
    except Exception:
        print("Output from wallet-bootstrap")
        print(log.getvalue().decode("utf-8"))
        raise
    finally:
        try:
            service.terminate()
        except ProcessLookupError:
            # Service died itself§
            pass
        # Let it die gracefully before we tear down database
        time.sleep(10)
        try:
            service.kill()
        except:
            pass
