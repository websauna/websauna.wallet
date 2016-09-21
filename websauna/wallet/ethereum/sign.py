"""Sign data with Ethereum private key.

Based on ethereum/tests/test_cotnracts.py
"""
import binascii

import bitcoin
from ethereum import utils
from ethereum.utils import big_endian_to_int, sha3
from secp256k1 import PrivateKey


def eth_privtoaddr(priv) -> str:
    """Generate Ethereum address from a private key.

    God, it was hard to find how this happens.

    https://github.com/ethereum/pyethsaletool/blob/master/pyethsaletool.py#L111

    :return: 0x prefixed hex string
    """
    pub = bitcoin.encode_pubkey(bitcoin.privtopub(priv), 'bin_electrum')
    return "0x" + binascii.hexlify(sha3(pub)[12:]).decode("ascii")


def sign(data: bytes, private_key_seed_ascii: str, hash_function=bitcoin.bin_sha256):
    """Sign data using Ethereum private key.

    :param private_key_seed_ascii: Private key seed as ASCII string
    """

    msghash = hash_function(data)

    priv = utils.sha3(private_key_seed_ascii)
    pub = bitcoin.privtopub(priv)

    # Based on ethereum/tesrt_contracts.py test_ecrecover
    pk = PrivateKey(priv, raw=True)

    signature = pk.ecdsa_recoverable_serialize(pk.ecdsa_sign_recoverable(msghash, raw=True))
    signature = signature[0] + utils.bytearray_to_bytestr([signature[1]])

    v = utils.safe_ord(signature[64]) + 27
    r_bytes = signature[0:32]
    r = big_endian_to_int(r_bytes)
    s_bytes = signature[32:64]
    s = big_endian_to_int(s_bytes)

    #: XXX Ethereum wants its address in different format
    addr = utils.big_endian_to_int(utils.sha3(bitcoin.encode_pubkey(pub, 'bin')[1:])[12:])

    return {
        "signature": signature,
        "v": v,
        "r": r,
        "s": s,
        "r_bytes": r_bytes,
        "s_bytes": s_bytes,
        "address_bitcoin": addr,
        "address_ethereum": eth_privtoaddr(priv),
        "public_key": pub,
        "hash": msghash,
        "payload": bytes([v] + list(r_bytes)+ list(s_bytes,))
    }


def verify(msghash: bytes, signature, public_key):
    """Verify that data has been signed with Etheruem private key.
    :param signature:
    :return:
    """

    V = utils.safe_ord(signature[64]) + 27
    R = big_endian_to_int(signature[0:32])
    S = big_endian_to_int(signature[32:64])

    return bitcoin.ecdsa_raw_verify(msghash, (V, R, S), public_key)

