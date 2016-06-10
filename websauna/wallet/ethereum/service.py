import threading
from uuid import UUID

from .ethjsonrpc import EthJsonRpc


class EthereumService:
    """Ethereum service takes care of synchronizing operations between intenral database and Ethereum daemon.

    We take a simple approach where we have one service / db running one single thread which does all operations serial manner.
    """

    def __init__(self, client: EthJsonRpc, asset_network_id: UUID):
        self.client = client
        self.asset_network_id = asset_network_id

    def get_pending_write_operations(self):
        pass

    def run_pending_write_operations(self):
        pass

    def run_event_cycle(self):
        pass

