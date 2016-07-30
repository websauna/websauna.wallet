"""Tokenized asset support."""
from decimal import Decimal
from eth_ipc_client import Client
from math import floor

from websauna.wallet.ethereum.contract import Contract
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached

DEFAULT_TOKEN_CREATION_GAS = 1500000


class TokenCreationError(Exception):
    pass


def get_token_contract_class() -> dict:
    name = "Token"
    contract_meta = get_compiled_contract_cached(name)
    return contract_meta


class Token:
    """Proxy object for a deployed token contract

    Allows creation of new token contracts as well accessing existing ones.
    """

    def __init__(self, contract: Contract, version=0, initial_txid=None):
        """
        :param contract: Populus Contract object for underlying token contract
        :param version: What is the version of the deployed contract.
        :param initial_txid: Set on token creation to the txid that deployed the contract. Only available objects accessed through create().
        """

        # Make sure we are bound to an address
        assert contract._meta.address
        self.contract = contract

        self.version = version

        self.initial_txid = initial_txid

    @property
    def address(self) -> str:
        """Get wallet address as 0x hex string."""
        return self.contract._meta.address

    @property
    def client(self) -> Client:
        """Get access to RPC client we are using for this wallet."""
        return self.contract._meta.blockchain_client

    def transfer(self, to_address: str, amount: Decimal) -> str:
        """Transfer tokens from the .

        Tokens must be owned by coinbase.

        :param amount: How much
        :param to_address: Address we are withdrawing to
        :return: Transaction id
        """
        amount = self.validate_transfer_amount(amount)
        return self.contract.transfer(to_address, amount)

    @classmethod
    def get(cls, rpc: Client, address: str, contract_factory=get_token_contract_class) -> "Token":
        """Get a proxy object to existing hosted token contract."""
        contract = contract_factory()
        assert address.startswith("0x")
        instance = contract(address, rpc)
        return Token(instance, rpc)

    @classmethod
    def create(cls, rpc: Client, name: str, symbol: str, supply: int, owner: str, wait_for_tx_seconds=90, gas=DEFAULT_TOKEN_CREATION_GAS, contract_factory=get_token_contract_class) -> "Token":
        """Creates a new token contract.

        The cost of deployment is paid from coinbase account.

        :param name: Asset name in contract

        :param symbol: Asset symbol in contract

        :param supply: How many tokens are created

        :param owner: Initial owner os the asset

        :param contract_factory: Which contract we deploy as Populus Contract class. Function that retunrns new Contract instance.

        :return: Populus Contract proxy object for new contract
        """

        assert owner.startswith("0x")

        version = 2  # Hardcoded for now

        contract = contract_factory()

        txid = deploy_contract(rpc, contract, gas=gas, constructor_args=[supply, name, 0, symbol, str(version), owner])

        if wait_for_tx_seconds:
            rpc.wait_for_transaction(txid, max_wait=wait_for_tx_seconds)
        else:
            # We cannot get contract address until the block is mined
            return (None, txid, version)

        try:
            contract_addr = get_contract_address_from_txn(rpc, txid)
        except ValueError:
            raise TokenCreationError("Could not create token with {} gas. Txid {}. Out of gas? Check in http://testnet.etherscan.io/tx/{}".format(DEFAULT_TOKEN_CREATION_GAS, txid, txid))

        instance = contract(contract_addr, rpc)
        return Token(instance, version=2, initial_txid=txid)

    @classmethod
    def validate_transfer_amount(cls, amount):
        assert isinstance(amount, Decimal)

        if amount - Decimal(floor(amount)) != 0:
            # TODO: Handle decimal units in contract units
            raise ValueError("Cannot transfer fractional tokens")

        amount = int(amount)
        return amount


