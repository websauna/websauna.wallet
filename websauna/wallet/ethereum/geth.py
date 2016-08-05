"""Helper to start geth in private net mode."""

import os

from populus.chain import TestingGethProcess
from populus.utils.chain import get_geth_logfile_path
from populus.utils.filesystem import get_blockchains_dir


def start_private_geth(chain_name, project_dir, host, port) -> TestingGethProcess:

    blockchains_dir = get_blockchains_dir(project_dir)

    os.makedirs(os.path.join(project_dir, "logs"), exist_ok=True)

    overrides = {
        "rpc_port": str(port),
        "rpc_addr": host,
    }

    geth = TestingGethProcess(
        chain_name=chain_name,
        base_dir=blockchains_dir,
        stdout_logfile_path=get_geth_logfile_path(project_dir, chain_name, 'stdout'),
        stderr_logfile_path=get_geth_logfile_path(project_dir, chain_name, 'stderr'),
        overrides=overrides
    )

    with geth as running_geth:
        if running_geth.is_mining:
            running_geth.wait_for_dag(600)
        if running_geth.ipc_enabled:
            running_geth.wait_for_ipc(30)
        if running_geth.rpc_enabled:
            running_geth.wait_for_rpc(30)

    return geth