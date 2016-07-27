"""Start/stop Ethereum service."""
import sys
from io import BytesIO

import pexpect


def test_start_service(test_config_path, dbsession, geth_node):
    """We can spawn a standalone Ethereum service."""
    log = BytesIO()
    child = pexpect.spawn('ethereum-service {}'.format(test_config_path), logfile=log)
    try:
        child.expect("Ethereum service started", timeout=10)
    except pexpect.exceptions.ExceptionPexpect:
        print(log.getvalue().decode("utf-8"))
        raise

