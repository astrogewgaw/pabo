"""
Numerical constructs.
"""

import struct
import numpy as np

from attrs import define
from numpy.typing import ArrayLike
from pabo.kernels import pack, unpack
from typing import IO, Union, Optional
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
    def __format__(self) -> str:
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

    def __size__(self) -> int:
        return self.width

    def __build__(
        self,
        data: int,
        stream: IO[bytes],
    ) -> None:
        stream.write(struct.pack(self.__format__, data))

    def __parse__(self, stream: IO[bytes]) -> int:
        return struct.unpack(self.__format__, stream.read(self.width))[0]

    def __mul__(self, count: int):
        if isinstance(count, int):
            return Array(self, count)
        else:
            raise PaboError("A Construct may only be multiplied by an integer.")

    def __rmul__(self, count: int):
        return self.__mul__(count)


@define
class Float(Construct):

    """
    Represents a fixed-width floating point number.
    """

    width: int
    endian: str = "little"

    @property
    def __format__(self) -> str:
        return "".join(
            [
                ">" if self.endian == "big" else "<",
                {4: "f", 8: "d"}.get(self.width, ""),
            ]
        )

    def __size__(self) -> int:
        return self.width

    def __build__(
        self,
        data: float,
        stream: IO[bytes],
    ) -> None:
        stream.write(struct.pack(self.__format__, data))

    def __parse__(self, stream: IO[bytes]) -> float:
        return struct.unpack(self.__format__, stream.read(self.width))[0]

    def __mul__(self, count: int):
        if isinstance(count, int):
            return Array(self, count)
        else:
            raise PaboError("A Construct may only be multiplied by an integer.")

    def __rmul__(self, count: int):
        return self.__mul__(count)


@define
class Array(Construct):

    """
    Represents an array of fixed-width numbers.
    """

    main: Union[Int, Float]
    count: int = -1
    packing: Optional[int] = None

    def __size__(self) -> int:
        return self.count

    def __build__(
        self,
        data: ArrayLike,
        stream: IO[bytes],
    ):
        array = np.asarray(data, dtype=self.main.__format__)
        if self.packing is not None:
            array = pack(array.flatten(), nbits=self.packing)
        stream.write(array.tobytes())

    def __parse__(self, stream: IO[bytes]) -> np.ndarray:
        data = stream.read(self.count)
        array = np.frombuffer(data, dtype=self.main.__format__)
        if self.packing is not None:
            array = unpack(array, nbits=self.packing)
        return array
