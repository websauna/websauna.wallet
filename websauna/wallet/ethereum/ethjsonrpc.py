import json

from eth_rpc_client import Client
from pyramid.registry import Registry


class EthJsonRpc(Client):
    """Customized JSON-RPC client."""

    def _serialize_json(self, obj):
        """Specialized encoding method to handle bytes correctly."""
        if type(obj) == bytes:
            return obj.decode("utf-8")
        raise TypeError()

    def construct_json_request(self, method, params):
        # Py3 fix so that bytes (sendTransaction data) are automatically utf-8 decoded as they are hex strings
        request = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.get_nonce(),
        }, default=self._serialize_json)
        return request


def get_eth_json_rpc_client(registry: Registry) -> EthJsonRpc:
    """Create a new Ethereum RPC client based on INI configuration."""
    assert isinstance(registry, Registry)
    host = registry.settings.get("ethereum.ethjsonrpc.host")
    port = registry.settings.get("ethereum.ethjsonrpc.port")
    assert host
    assert port
    return EthJsonRpc(host, port)


def get_unlocked_json_rpc_client(registry: Registry) -> EthJsonRpc:
    """Get unsafe JSON-RPC access to geth.

    Unlocks coinbase account.

    You must run geth as::

        ./geth --testnet --fast --rpc --rpcapi "db,eth,net,web3,personal"

    """
    client = get_eth_json_rpc_client(registry)

    # Perform unlock over RPC
    # http://ethereum.stackexchange.com/a/1414/620
    password = registry.settings.get("ethereum.ethjsonrpc.unlock_password", "")
    unlock_seconds = int(registry.settings.get("ethereum.ethjsonrpc.unlock_seconds", 24*3600))

    coinbase = client.get_coinbase()  # Get primary account we are using
    # https://github.com/ethereum/go-ethereum/wiki/Management-APIs#personal_unlockaccount
    client.make_request("personal_unlockAccount", [coinbase, password, unlock_seconds])

    return client

