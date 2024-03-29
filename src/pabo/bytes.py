"""
Byte manipulation.
"""

from attrs import define
from pabo.wrappers import Const
from pabo.base import Construct


@define
class Bytes(Construct):

    """
    Represents bytes.
    """

    size: int

    def __size__(self):
        return self.size

    def __build__(self, data, stream) -> None:
        stream.write(data)

    def __parse__(self, stream):
        return stream.read(self.size)


@define
class Flag(Construct):

    """
    Represents a single byte as a boolean.
    """

    def __size__(self) -> int:
        return 1

    def __build__(self, data, stream) -> None:
        stream.write(b"\x01" if data else b"\x00")

    def __parse__(self, stream):
        data = stream.read(1)
        return data != b"\x00"


def Padding(size):

    """
    Represents padding via zero bytes (b"\x00").
    """

    return Const(b"\x00" * size, Bytes(size))
