"""Start/stop Ethereum service."""
import sys
from io import BytesIO

import pexpect


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

    service = pexpect.spawn('ethereum-service {}'.format(test_config_path))

    log = BytesIO()
    bootstrap = pexpect.spawn('wallet-bootstrap {}'.format(test_config_path), logfile=log)

    try:
        bootstrap.expect("Bootstrap complete", timeout=30)
    except pexpect.exceptions.ExceptionPexpect:
        print(log.getvalue().decode("utf-8"))
        raise

    service.terminate()