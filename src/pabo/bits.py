"""
Bit manipulation.
"""

import numpy as np

from typing import IO
from attrs import define
from pabo.base import PaboError, Construct
from pabo.kernels import pack, unpack, swaps


@define
class Bits(Construct):

    """
    Represents bits.
    """

    size: int
    swap: bool = False

    def __size__(self) -> int:
        return self.size

    def __build__(
        self,
        bits: bytes,
        stream: IO[bytes],
    ) -> None:
        data = np.frombuffer(bits, dtype=np.uint8)
        data = data[: self.size]
        data = pack(data, nbits=1)
        if self.swap:
            data = swaps(data)
        data = data.tobytes()
        stream.write(data)

    def __parse__(self, stream: IO[bytes]) -> bytes:
        raw = stream.read(self.size // 8)
        data = np.frombuffer(raw, dtype=np.uint8)
        data = data[: self.size]
        data = unpack(data, nbits=1)
        if self.swap:
            data = swaps(data)
        data = data.tobytes()
        return data
