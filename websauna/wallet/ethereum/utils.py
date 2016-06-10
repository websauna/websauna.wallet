from typing import List

from Crypto.Hash import keccak

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


def bin_to_txid(b: bytes):
    i = int.from_bytes(b, byteorder="big")
    # http://stackoverflow.com/a/12638477/315168
    return "{0:#0{1}x}".format(i, 42)


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

