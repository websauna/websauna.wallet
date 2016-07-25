from typing import List

from Crypto.Hash import keccak
from decimal import Decimal

sha3_256 = lambda x: keccak.new(digest_bits=256, data=x).digest()


def bin_to_eth_address(b: bytes):
    i = int.from_bytes(b, byteorder="big")
    # http://stackoverflow.com/a/12638477/315168
    return "{0:#0{1}x}".format(i, 42)


def eth_address_to_bin(s: str) -> bytes:
    i = int(s, 16)
    return i.to_bytes(length=160//8, byteorder="big")


def txid_to_bin(s: str) -> bytes:
    i = int(s, 16)
    return i.to_bytes(length=256//8, byteorder="big")


def bin_to_txid(b: bytes) -> str:
    """Convert binary presentation of transaction hash to 0x strings for RPC."""
    i = int.from_bytes(b, byteorder="big")
    # http://stackoverflow.com/a/12638477/315168
    tx_hash = "{0:#0{1}x}".format(i, 66)
    assert len(tx_hash) == 66, "Transaction has must be padded to 32 bytes, got {}".format(tx_hash)
    return tx_hash


def bin_to_uint256(b: bytes) -> int:
    i = int.from_bytes(b, byteorder="big")
    return i


def uint256_to_bin(i) -> int:
    return i.to_bytes(length=256//8, byteorder="big")


def split_256_bit_data_chunks(s: str) -> List[bytes]:
    """Split 4x uint256 data tuple used in changes events."""
    assert s[0:2] == "0x"
    raw = s[2:]
    data = bytearray.fromhex(raw)

    result = []
    while data:
        result.append(data[0:32])
        data = data[32:]
    return result


def sha3(seed: str):
    return sha3_256(seed)


def to_wei(amount_in_ether: Decimal):
    """http://forum.ethereum.org/discussion/304/what-is-wei"""
    assert isinstance(amount_in_ether, Decimal)
    return int(amount_in_ether * 10**18)


def wei_to_eth(amount_in_wei: int):
    return Decimal(amount_in_wei) / Decimal(10**18)
