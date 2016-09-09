"""Helper to start geth in private net mode."""

import os
import logging

from populus.chain import LoggedDevGethProcess
from populus.utils.chains import get_geth_logfile_path
from populus.utils.filesystem import get_blockchains_dir


logger = logging.getLogger(__name__)


def start_private_geth(chain_name, project_dir, host, port, verbosity=5, p2p_port=30303):
    """Start a local geth process that mines isolated private testnet."""
    blockchains_dir = get_blockchains_dir(project_dir)

    os.makedirs(os.path.join(project_dir, "logs"), exist_ok=True)

    overrides = {
        "rpc_port": str(port),
        "rpc_addr": host,
        "ipc_disable": "true",
        "verbosity": str(verbosity),  # https://github.com/ethereum/go-ethereum/wiki/Command-Line-Options
        "port": str(p2p_port)
    }

    geth = LoggedDevGethProcess(
        chain_name=chain_name,
        project_dir=project_dir,
        blockchains_dir=blockchains_dir,
        overrides=overrides
    )

    logger.info("Starting geth")
    geth.start()

    if geth.is_mining:
        logger.info("Waiting for DAG")
        geth.wait_for_dag(600)
    if geth.ipc_enabled:
        logger.info("Waiting for IPC")
        geth.wait_for_ipc(30)
    if geth.rpc_enabled:
        logger.info("Waiting for RPC")
        geth.wait_for_rpc(30)

    return geth