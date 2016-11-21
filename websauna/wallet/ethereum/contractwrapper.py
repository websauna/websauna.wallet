from decimal import Decimal
from typing import Optional

from web3 import Web3
from web3.contract import construct_contract_factory

from websauna.wallet.ethereum.contract import deploy_contract, Contract
from websauna.wallet.ethereum.populuslistener import get_contract_events
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
    def abi_factory(cls, contract_name: Optional[str]=None) -> dict:
        """A method to give us ABI descriptino for the contract."""
        raise NotImplementedError()

    @classmethod
    def contract_class(cls, web3: Web3, contract_name=None) -> type:
        """Get web3 bound instance of a Contract proxy class."""
        contract_definition = cls.abi_factory(contract_name)
        contract_class = construct_contract_factory(
            web3=web3,
            abi=contract_definition["abi"],
            code=contract_definition["code"],
            code_runtime=contract_definition["code_runtime"],
            source=contract_definition["source"],
        )
        return contract_class

    @classmethod
    def get(cls, web3: Web3, address: str, contract_name=None) -> "ContractWrapper":
        """Get a proxy object to existing hosted wallet contrac.t"""

        contract = cls.contract_class(web3, contract_name)
        assert address.startswith("0x")
        instance = contract(address=address)
        # Create new ContractWrapper around the contract
        return cls(instance)

    @classmethod
    def create(cls, web3: Web3, wait_for_tx_seconds=180, gas=1500000, args=None, contract_name=None) -> "ContractWrapper":
        """Creates a new hosted wallet.

        The cost of deployment is paid from coinbase account.

        :param contract_factory: Which contract we deploy as Populus Contract class. Function that retunrns new Contract instance.

        :return: Populus Contract proxy object for new contract
        """
        contract_class = cls.abi_factory(contract_name)

        if not args:
            args = []

        contract, txid = deploy_contract(web3, contract_class, gas=gas, timeout=wait_for_tx_seconds, constructor_arguments=args)

        # Use hardcoded version for now
        return cls(contract, version=2, initial_txid=txid)

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

    def get_all_events(self):
        """Helper to map getTransactionReceipt() logs to human readable."""
        events = get_contract_events(self.contract)
        return {event.name: hex(key) for key, event in events}

    def dump_all_events(self):
        """Debug function to inspect what happens inside the contract transactions."""
        events = get_contract_events(self.contract)
        for key, event in events:
            print(hex(key), event.name)
