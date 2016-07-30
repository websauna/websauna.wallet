from decimal import Decimal
from web3 import Web3

from websauna.wallet.ethereum.contract import deploy_contract, Contract
from websauna.wallet.ethereum.utils import wei_to_eth


class ContractWrapper:
    """Simple wrapper around smart contracts."""

    def __init__(self, contract: Contract, version=0, initial_txid=None):
        """
        :param wallet_contract: Populus Contract object for underlying wallet contract
        :param version: What is the version of the deployed contract.
        :param initial_txid: Set on wallet creation to the txid that deployed the contract. Only available objects accessed through create().
        """

        # Make sure we are bound to an address
        assert contract.address
        self.contract = contract

        self.version = version

        self.initial_txid = initial_txid

    @classmethod
    def abi_factory(cls):
        """A method to give us ABI descriptino for the contract."""
        raise NotImplementedError()

    @classmethod
    def get(cls, web3: Web3, address: str) -> "ContractWrapper":
        """Get a proxy object to existing hosted wallet contrac.t"""

        contract = cls.abi_factory()
        assert address.startswith("0x")
        instance = contract(address, web3)
        return ContractWrapper(instance, web3)

    @classmethod
    def create(cls, web3: Web3, wait_for_tx_seconds=90, gas=1500000) -> "ContractWrapper":
        """Creates a new hosted wallet.

        The cost of deployment is paid from coinbase account.

        :param contract_factory: Which contract we deploy as Populus Contract class. Function that retunrns new Contract instance.

        :return: Populus Contract proxy object for new contract
        """
        contract_class = cls.abi_factory()

        contract, txid = deploy_contract(web3, contract_class, gas=gas, timeout=wait_for_tx_seconds)

        # Use hardcoded version for now
        return ContractWrapper(contract, version=2, initial_txid=txid)

    @property
    def address(self) -> str:
        """Get wallet address as 0x hex string."""
        return self.contract.address

    @property
    def web3(self) -> Web3:
        """Get access to RPC client we are using for this wallet."""
        return self.contract.web3

    def get_balance(self) -> Decimal:
        """Gets the balance on this contract address over RPC and converts to ETH."""
        return wei_to_eth(self.web3.eth.getBalance(self.address))
