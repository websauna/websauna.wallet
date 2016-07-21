"""Initialize local test geth node so that we can use it for mining.

"""
import os
import pytest

from populus.geth import wait_for_geth_to_create_dag

pytest_plugins = "populus.plugin",


@pytest.mark.skipif(not os.environ.get("GETH_BOOTSTRAP"),
                    reason="Bootstrapping geth blockchain files is very slow operation and we want to run it only once.")
def test_initialize_geth_node(geth_node_command: tuple, geth_coinbase):
    """Faux test case to create default-chain folder and initial mining files."""
    command, proc = geth_node_command

    # This will keep printing geth status updates until DAG files have
    # been created
    wait_for_geth_to_create_dag(proc)