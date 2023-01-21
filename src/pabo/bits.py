"""
Bit manipulation.
"""

import numpy as np

from attrs import define
from pabo.base import Construct
from pabo.core import pack, unpack, swap


@define
class Bits(Construct):

    """
    Represents bits.
    """

    size: int
    swap: bool = False

    def __size__(self):
        return self.size

    def __build__(self, bits, stream):
        data = np.frombuffer(bits, dtype=np.uint8)
        data = data[: self.size]
        data = pack(data, nbits=1)
        if self.swap:
            data = swap(data)
        data = data.tobytes()
        stream.write(data)

    def __parse__(self, stream):
        raw = stream.read(self.size // 8)
        data = np.frombuffer(raw, dtype=np.uint8)
        data = data[: self.size]
        data = unpack(data, nbits=1)
        if self.swap:
            data = swap(data)
        data = data.tobytes()
        return data
