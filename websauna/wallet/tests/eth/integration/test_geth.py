"""Start/stop Ethereum service."""
import os
import pytest
import time

from web3 import Web3, RPCProvider

from websauna.wallet.ethereum.geth import start_private_geth


def test_start_private_geth(test_config_path, dbsession):
    """We can spawn a standalone private geth instance for private testnet."""

    project_dir = os.getcwd() # Goes under "chains"
    geth = start_private_geth("foobar", project_dir, "127.0.0.1", 10010)

    web3 = Web3(RPCProvider("127.0.0.1", 10010))

    deadline = time.time() + 10

    while time.time() < deadline:

        if not geth.is_alive:
            pytest.fail("geth died")

        try:
            web3.eth.coinbase
            geth.stop()
            return
        except Exception as e:
            print(e)
        time.sleep(1)

    geth.stop()
    pytest.fail("Could not connect to geth instance using a specific port")
