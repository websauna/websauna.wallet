# Lifted from Populus 0.8.0 for event decoding support

import binascii
import re

from ethereum import utils as ethereum_utils
from ethereum import abi


def decode_single(typ, data):
    base, sub, _ = abi.process_type(typ)

    # ensure that we aren't trying to decode an empty response.
    assert len(data) > 2

    if base == 'address':
        return '0x' + strip_0x_prefix(data[-40:])
    elif base == 'string' or base == 'bytes' or base == 'hash':
        if sub:
            bytes = ethereum_utils.int_to_32bytearray(int(data, 16))
            while bytes and bytes[-1] == 0:
                bytes.pop()
            if bytes:
                return ''.join(chr(b) for b in bytes)
        else:
            num_bytes = int(data[64 + 2:128 + 2], 16)
            bytes_as_hex = data[2 + 128:2 + 128 + (2 * num_bytes)]
            return ethereum_utils.decode_hex(bytes_as_hex)
    elif base == 'uint':
        return int(data, 16)
    elif base == 'int':
        o = int(data, 16)
        return (o - 2 ** int(sub)) if o >= 2 ** (int(sub) - 1) else o
    elif base == 'ureal':
        raise NotImplementedError('havent gotten to this')
        high, low = [int(x) for x in sub.split('x')]
        # return big_endian_to_int(data) * 1.0 / 2 ** low
    elif base == 'real':
        raise NotImplementedError('havent gotten to this')
        high, low = [int(x) for x in sub.split('x')]
        # return (big_endian_to_int(data) * 1.0 / 2 ** low) % 2 ** high
    elif base == 'bool':
        return bool(int(data, 16))
    else:
        raise ValueError("Unknown base: `{0}`".format(base))


def decode_multi(types, outputs):
    res = abi.decode_abi(
        types,
        binascii.a2b_hex(strip_0x_prefix(outputs)),
    )
    processed_res = [
        "0x" + strip_0x_prefix(v) if t == "address" else v
        for t, v in zip(types, res)
    ]
    return processed_res


def strip_0x_prefix(value):

    if type(value) == bytes:
        value = value.decode("ascii")

    if value.startswith('0x'):
        return value[2:]
    return value


def clean_args(*args):
    for _type, arg in args:
        if _type == 'address':
            yield strip_0x_prefix(arg)
        else:
            yield arg
