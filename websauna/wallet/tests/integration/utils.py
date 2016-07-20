from populus.contracts import deploy_contract
from populus.utils import get_contract_address_from_txn
from websauna.wallet.ethereum.wallet import get_wallet_contract_class


NETWORK_PARAMETERS = {
    "geth_local": {

    },

    "testnet": {

    }
}

def wait_tx(eth_json_rpc, txid):
    try:
        eth_json_rpc.wait_for_transaction(txid, max_wait=90.0)
    except ValueError as e:
        raise ValueError("Could not broadcast transaction {}".format(txid)) from e


def deploy_contract_tx(client, geth_node, geth_coinbase, contract: type) -> str:
    """Deploy a contract.

    :return: Deployed contract address
    """

    # Make sure that we have at least one block mined
    client.wait_for_block(1)

    # Make sure we have some ETH on coinbase account
    # so that we can deploy a contract
    assert client.get_balance(geth_coinbase) > 0

    # Get a transaction hash where our contract is deployed.
    # We set gas to very high randomish value, to make sure we don't
    # run out of gas when deploying the contract.
    deploy_txn_hash = deploy_contract(client, contract, gas=1500000)

    # Wait that the geth mines a block with the deployment
    # transaction
    client.wait_for_transaction(deploy_txn_hash)

    contract_addr = get_contract_address_from_txn(client, deploy_txn_hash)

    return contract_addr


def deploy_wallet(client, geth_node, get_coinbase):
    # We define the Populus Contract class outside the scope
    # of this example. It would come from compiled .sol
    # file loaded through Populus framework contract
    # mechanism.
    contract = get_wallet_contract_class()
    return deploy_contract_tx(client, geth_node, get_coinbase, contract)
