"""
Byte manipulation.
"""

from dataclasses import dataclass

from pabo.base import Construct, readexact
from pabo.context import Dynamic, evaluate
from pabo.errors import PaboError, SizeofError, ValidationError
from pabo.wrappers import Const


def _count(value, ctx) -> int:
    count = evaluate(value, ctx)
    if not isinstance(count, int):
        raise PaboError(f"The count must be an integer, got {count!r}.")
    return count


@dataclass
class Bytes(Construct[bytes]):
    """
    Represents `count` raw bytes.

    `count` may depend on other fields (`Bytes(this.length)`). A negative
    `count` reads until the end of the stream. Building checks that the data
    has exactly `count` bytes.
    """

    count: Dynamic

    def _size(self, ctx):
        count = _count(self.count, ctx)
        if count < 0:
            raise SizeofError("Greedy bytes have no fixed size.")
        return count

    def _build(self, data, stream, ctx):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ValidationError(f"Expected bytes, got {type(data).__name__}.")
        count = _count(self.count, ctx)
        if count >= 0 and len(data) != count:
            raise ValidationError(f"Expected {count} bytes, got {len(data)}.")
        stream.write(data)
        return data

    def _parse(self, stream, ctx) -> bytes:
        count = _count(self.count, ctx)
        if count < 0:
            return stream.read()
        return readexact(stream, count)


@dataclass
class Flag(Construct[bool]):
    """
    Represents a single byte as a boolean.

    Any non-zero byte parses as True. Building writes 1 for a true value and 0
    for a false one.
    """

    def _size(self, ctx) -> int:
        return 1

    def _build(self, data, stream, ctx):
        stream.write(b"\x01" if data else b"\x00")
        return bool(data)

    def _parse(self, stream, ctx) -> bool:
        return readexact(stream, 1) != b"\x00"


def GreedyBytes() -> Bytes:
    """
    Represents all the bytes up to the end of the stream.
    """

    return Bytes(-1)


def Padding(size: int) -> Const:
    """
    Represents padding via zero bytes (b"\\x00").
    """

    return Const(b"\x00" * size, Bytes(size))
