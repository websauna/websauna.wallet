"""Testing ecrecover() inside a contract using Populus framework."""
import binascii

import pytest

# How many ETH we move for test transactiosn
from ethereum.utils import big_endian_to_int
from web3 import Web3
from web3.contract import Contract
from websauna.wallet.ethereum.compiler import get_compiled_contract_cached
from websauna.wallet.ethereum.contract import confirm_transaction, deploy_contract
from websauna.wallet.ethereum.sign import sign, verify
from websauna.wallet.tests.eth.utils import wait_tx, create_contract_listener

# 0x037844c81dc99356cf66e5b6d03e0c6cd7d099cc
#

@pytest.fixture()
def signature_contract(web3):
    contract_def = get_compiled_contract_cached("SignatureVerifier")
    contract, txid = deploy_contract(web3, contract_def)
    return contract


def test_signature_internal():
    """Test that our signature verification works in pure Python.

    Note that this uses bitcoin.ecdsa_raw_verify() which takes public key as public key format, not address.
    """

    # Use random Ethereum address as payload for signing
    data = "0xda39147df55f6c51ad539a5e108adc5d7284b309"

    # Convert address to raw bytes
    data_bin = binascii.unhexlify(data[2:])
    assert type(data_bin) == bytes

    private_key_seed = "foobar"

    signature_data = sign(data_bin, private_key_seed)
    print(signature_data)

    assert verify(signature_data["hash"], signature_data["signature"], signature_data["public_key"])


def test_signature_contract_verify_v_r_s(web3: Web3, signature_contract: Contract):
    """Test that our signature verification works in Solidity contract.

    """

    # Use random Ethereum address as payload for signing
    data = "0xda39147df55f6c51ad539a5e108adc5d7284b309"

    # Convert address to raw bytes
    data_bin = binascii.unhexlify(data[2:])
    assert type(data_bin) == bytes

    private_key_seed = "foobar"
    # Address is 0x58708390680239282143999941903085911172379991841

    signature_data = sign(data_bin, private_key_seed)

    # hash = big_endian_to_int(signature_data["hash"])
    hash = signature_data["hash"]
    v = signature_data["v"]
    r = signature_data["r_bytes"]
    s = signature_data["s_bytes"]

    # 0x0a489345f9e9bc5254e18dd14fa7ecfdb2ce5f21
    result = signature_contract.call().verify(hash, v, r, s)
    assert result == signature_data["address_ethereum"]


