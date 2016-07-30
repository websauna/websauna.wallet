from typing import Optional, Tuple

from web3 import Web3
from web3.contract import _Contract, construct_contract_class

from populus.utils.transactions import get_contract_address_from_txn


class Contract(_Contract):
    """Statically typing helper for contract class.

    May contain methods in the future.
    """
    pass



def deploy_contract(
        web3: Web3,
        contract_definition: dict,
        gas=1500000,
        timeout=60.0,
        constructor_arguments: Optional[list]=None,
        from_account=None) -> Tuple[_Contract, str]:
    """Deploys a single contract using Web3 client.

    :param web3: Web3 client instance

    :param contract_definition: Dictionary of describing the contract interface,
        as read from ``contracts.json`` Contains

    :param gas: Max gas

    :param timeout: How many seconds to wait the transaction to
        confirm to get the contract address.

    :param constructor_arguments: Arguments passed to the smart contract
        constructor. Automatically encoded through ABI signature.

    :param from_account: Geth account that's balance is used for deployment.
        By default, the gas is spent from Web3 coinbase account. Account must be unlocked.

    :return: Tuple containing Contract proxy object and the transaction hash where it was deployed

    :raise gevent.timeout.Timeout: If we can't get our contract in a block within given timeout
    """

    # Check we are passed valid contract definition
    assert "abi" in contract_definition, \
        "Please pass a valid contract definition dictionary, got {}".format(contract_definition)

    contract_class = construct_contract_class(
        web3=web3,
        abi=contract_definition["abi"],
        code=contract_definition["code"],
        code_runtime=contract_definition["code_runtime"],
        source=contract_definition["source"],
            )

    if not from_account:
        from_account = web3.eth.coinbase

    # Set transaction parameters
    transaction = {
        "gas": gas,
        "from": from_account,
    }

    # Call web3 to deploy the contract
    txn_hash = contract_class.deploy(transaction, constructor_arguments)

    # Wait until we get confirmation and address
    address = get_contract_address_from_txn(web3, txn_hash, timeout=timeout)

    # Create Contract proxy object
    contract = contract_class(
        address=address,
        abi=contract_definition["abi"],
        code=contract_definition["code"],
        code_runtime=contract_definition["code_runtime"],
        source=contract_definition["source"])

    return contract, txn_hash



