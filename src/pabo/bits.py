"""
Bit manipulation.
"""

from dataclasses import dataclass

import numpy as np

from pabo.base import Construct, read_exactly
from pabo.errors import PaboError, ValidationError
from pabo.numeric import BitOrder, _check_bitorder
from pabo.packed import pack, unpack


@dataclass
class Bits(Construct):
    """
    Represents `count` bits, as bytes with one 0 or 1 per bit.

    The bits occupy ceil(count / 8) bytes, so `size` is in bytes, like every
    other construct. Unused trailing bits are zero when building and ignored
    when parsing. `bitorder` decides whether the first bit is the most ("big")
    or least ("little") significant bit of each byte.
    """

    count: int
    bitorder: BitOrder = "big"

    def __post_init__(self):
        if self.count < 0:
            raise PaboError("The number of bits cannot be negative.")
        _check_bitorder(self.bitorder)

    def _size(self, ctx):
        return -(-self.count // 8)

    def _build(self, bits, stream, ctx):
        if isinstance(bits, (bytes, bytearray, memoryview)):
            values = np.frombuffer(bits, dtype=np.uint8)
        else:
            values = np.asarray(bits, dtype=np.uint8).ravel()
        if values.size != self.count:
            raise ValidationError(f"Expected {self.count} bits, got {values.size}.")
        if (values > 1).any():
            raise ValidationError("Bits must be 0 or 1.")
        padded = np.zeros(self.size * 8, dtype=np.uint8)
        padded[: self.count] = values
        stream.write(pack(padded, nbits=1, bitorder=self.bitorder).tobytes())
        return bits

    def _parse(self, stream, ctx):
        raw = read_exactly(stream, self.size)
        bits = unpack(np.frombuffer(raw, dtype=np.uint8), nbits=1, bitorder=self.bitorder)
        return bits[: self.count].tobytes()
