"""
Byte manipulation.
"""

from dataclasses import dataclass

from pabo.base import Construct, PaboError, read_exactly
from pabo.wrappers import Const


@dataclass
class Bytes(Construct):
    """
    Represents bytes. A negative `count` reads until the end of the stream.
    """

    count: int

    def _size(self):
        if self.count < 0:
            raise PaboError("Greedy bytes have no fixed size.")
        return self.count

    def _build(self, data, stream) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise PaboError(f"Expected bytes, got {type(data).__name__}.")
        if self.count >= 0 and len(data) != self.count:
            raise PaboError(f"Expected {self.count} bytes, got {len(data)}.")
        stream.write(data)

    def _parse(self, stream) -> bytes:
        if self.count < 0:
            return stream.read()
        return read_exactly(stream, self.count)


@dataclass
class Flag(Construct):
    """
    Represents a single byte as a boolean.
    """

    def _size(self) -> int:
        return 1

    def _build(self, data, stream) -> None:
        stream.write(b"\x01" if data else b"\x00")

    def _parse(self, stream) -> bool:
        return read_exactly(stream, 1) != b"\x00"


def Padding(size):
    """
    Represents padding via zero bytes (b"\x00").
    """

    return Const(b"\x00" * size, Bytes(size))
