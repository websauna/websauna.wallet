"""Tokenized asset support."""
from decimal import Decimal
from math import floor
import logging
from web3 import Web3

from websauna.wallet.ethereum.compiler import get_compiled_contract_cached
from websauna.wallet.ethereum.contractwrapper import ContractWrapper


logger = logging.getLogger(__name__)


class Token(ContractWrapper):
    """Proxy object for a deployed token contract

    Allows creation of new token contracts as well accessing existing ones.
    """

    @classmethod
    def abi_factory(cls, contract_name=None):
        contract_name = contract_name or "Token"
        contract_meta = get_compiled_contract_cached(contract_name)
        return contract_meta

    def transfer(self, to_address: str, amount: Decimal) -> str:
        """Transfer tokens from the .

        Tokens must be owned by coinbase.

        :param amount: How much
        :param to_address: Address we are withdrawing to
        :return: Transaction id
        """
        amount = self.validate_transfer_amount(amount)
        return self.contract.transact().transfer(to_address, amount)

    @classmethod
    def validate_transfer_amount(cls, amount):
        assert isinstance(amount, Decimal)

        if amount - Decimal(floor(amount)) != 0:
            # TODO: Handle decimal units in contract units
            raise ValueError("Cannot transfer fractional tokens")

        amount = int(amount)
        return amount

    @classmethod
    def create_token(cls, web3: Web3, name, supply, symbol, owner, wait_for_tx_seconds=180, gas=1500000, extra_arguments=None, contract_name=None) -> "Token":

        assert web3

        if isinstance(supply, Decimal):
            supply = int(supply)

        # TODO: Clean up construction arguments to be coherent across the codebase
        args = [supply, name, 0, symbol, "2", owner]
        if extra_arguments:
            args += extra_arguments

        logger.info("Creating token contract %s, arguments %s", contract_name, args)

        # [0, 'Mootoken', 0, 'MOO', '2', '0xccd5b1a54b00e50846a49307b655fe9b831927eb', '0xccd5b1a54b00e50846a49307b655fe9b831927eb', '0x5589C14FbC92A73809fBCfF33Ab40eFc7E8E8467', 6000000000000000000000, 2, 1000000000000000000]

        #  uint256, string, uint8, string, string, address, address, address, uint256, uint256, uint256

        return cls.create(web3, wait_for_tx_seconds=wait_for_tx_seconds, gas=gas, args=args, contract_name=contract_name)



