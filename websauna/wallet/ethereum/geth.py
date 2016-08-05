"""Helper to start geth in private net mode."""

import os

from populus.chain import TestingGethProcess
from populus.utils.chain import get_geth_logfile_path
from populus.utils.filesystem import get_blockchains_dir


def start_private_geth(chain_name, project_dir, host, port, verbosity=2, p2p_port=30303) -> TestingGethProcess:
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

    geth = TestingGethProcess(
        chain_name=chain_name,
        base_dir=blockchains_dir,
        stdout_logfile_path=get_geth_logfile_path(project_dir, chain_name, 'stdout'),
        stderr_logfile_path=get_geth_logfile_path(project_dir, chain_name, 'stderr'),
        overrides=overrides
    )

    geth.start()

    if geth.is_mining:
        geth.wait_for_dag(600)
    if geth.ipc_enabled:
        geth.wait_for_ipc(30)
    if geth.rpc_enabled:
        geth.wait_for_rpc(4)

    return geth