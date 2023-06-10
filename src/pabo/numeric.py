"""
Numerical constructs.
"""

import struct
import numpy as np

from attrs import define
from typing import Union, Optional
from pabo.core import pack, unpack
from pabo.base import PaboError, Construct


@define
class Int(Construct):

    """
    Represents a fixed-width integer.
    """

    width: int
    signed: bool = False
    endian: str = "little"

    @property
    def __format__(self):
        fmt = "".join(
            [
                ">" if self.endian == "big" else "<",
                {
                    1: "b",
                    2: "h",
                    4: "i",
                    8: "q",
                }.get(self.width, ""),
            ]
        )
        return fmt if self.signed else fmt.upper()

    def __size__(self):
        return self.width

    def __build__(self, data, stream) -> None:
        stream.write(struct.pack(self.__format__, data))

    def __parse__(self, stream):
        return struct.unpack(self.__format__, stream.read(self.width))[0]


@define
class Float(Construct):

    """
    Represents a fixed-width floating point number.
    """

    width: int
    endian: str = "little"

    @property
    def __format__(self):
        return "".join(
            [
                ">" if self.endian == "big" else "<",
                {4: "f", 8: "d"}.get(self.width, ""),
            ]
        )

    def __size__(self):
        return self.width

    def __build__(self, data, stream) -> None:
        stream.write(struct.pack(self.__format__, data))

    def __parse__(self, stream):
        return struct.unpack(self.__format__, stream.read(self.width))[0]


@define
class Array(Construct):

    """
    Represents an array of fixed-width numbers.
    """

    main: Union[Int, Float]
    count: int = -1
    packing: Optional[int] = None

    def __size__(self):
        return self.count

    def __build__(self, data, stream):
        if len(data) < self.count:
            raise PaboError("Not enough data to build.")
        data = data[: self.count] if self.count > 0 else data
        array = np.asarray(data, dtype=self.main.__format__)
        if self.packing is not None:
            array = pack(array.flatten(), nbits=self.packing)
        stream.write(array.tobytes())

    def __parse__(self, stream):
        data = stream.read(self.count * self.main.width if self.count > 0 else -1)
        if len(data) < self.count:
            raise PaboError("Not enough data to parse.")
        array = np.frombuffer(data, dtype=self.main.__format__)
        if self.packing is not None:
            array = unpack(array, nbits=self.packing)
        return array
