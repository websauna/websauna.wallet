"""Decode Ethereum raw transaction.

"""
from populus.contracts import Function


def find_abi(contract: type, signature: bytes) -> Function:
    """Check if contract class implements an ABI method of a certain type.

    Ethereum contract function signature is 4 bytes.
    """

    # http://stackoverflow.com/a/34452/315168
    methods = [getattr(contract, method) for method in dir(contract) if callable(getattr(contract, method))]

    for m in methods:
        # Only Contract proxy functions have abi_signature set
        if getattr(m, "encoded_abi_signature", None) == signature:
            return m

    return None


def decode_tx_input(contract_class: type, input_data: str) -> dict:
    """Convert transaction input hex string to symbolic presentation what ABI method is being called."""

    assert input_data.startswith("0x")
    bin = bytearray.fromhex(input_data[2:])

    # Method id is the first 4 bytes
    # http://ethereum.stackexchange.com/a/1171/620
    method_id = bin[0:4]

    abi = find_abi(contract_class, method_id)
    if not abi:
        raise ValueError("Contract class {} does not implement ABI method for signature {}".format(contract_class, input_data[2:10]))


if __name__ == "__main__":
    # Use Populus framework to create a Contract proxy class
    from websauna.wallet.ethereum.wallet import get_wallet_contract_class
    contract_class = get_wallet_contract_class()  # Wallet contract from simplewallet.sol
    # http://testnet.etherscan.io/tx/0x1e45d2c989d32e3f191ffac96f23be00b8ae87b8bdd18f2f65ca2dc3b7c81a67
    input_data = "0x62225c7862365c783164275c7866362262275c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c786461395c7831347d5c7866355f6c515c786164535c7839615e5c7831305c7838615c7864635d725c7838345c7862335c745c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830316345785d5c7838615c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c783030605c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c7830305c78303027"
    print(decode_tx_input(contract_class, input_data))