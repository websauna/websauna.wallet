import pytest

from websauna.wallet.ethereum.ethjsonrpc import get_unlocked_json_rpc_client
from websauna.wallet.ethereum.ops import register_eth_operations
from websauna.wallet.ethereum.service import EthereumService


@pytest.fixture
def eth_json_rpc(registry):
    """Create Ethereum RPC connection for integration tests."""
    return get_unlocked_json_rpc_client(registry)


