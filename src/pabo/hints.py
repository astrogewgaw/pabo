"""
Type hints shared across pabo.

beartype checks these at runtime, so a construct given the wrong kind of
argument fails as soon as it is created. The stream protocols only check that
the object has the right method (`read` or `write`), so any binary file,
`io.BytesIO`, socket file or `mmap.mmap` qualifies.

The aliases are:

- ``BytesLike``: ``bytes``, ``bytearray`` or ``memoryview``.
- ``Source``: what ``parse`` reads from (bytes, a path, or a ``Readable``).
- ``Target``: where ``build`` writes to (None, a path, or a ``Writable``).
- ``Endian``: ``"little"``, ``"big"`` or ``"native"``.
- ``BitOrder``: ``"big"`` or ``"little"``.
- ``NBits``: 1, 2 or 4, the bit widths that can be packed.
- ``Side``: ``"right"`` or ``"left"``.
- ``Whence``: 0, 1 or 2, as for ``io.IOBase.seek``.
- ``ContextFunction``: a function of the context.
- ``Dynamic``: an int, or a function of the context giving one.
- ``Condition``: a bool, or a function of the context.
- ``Key``: a hashable value, or a function of the context.
- ``Predicate``: a function of a value and the context.
"""

from collections.abc import Callable, Hashable
from os import PathLike
from typing import Any, Literal, Protocol, runtime_checkable

from pabo.context import Context


@runtime_checkable
class Readable(Protocol):
    """
    A binary stream that can be read from.
    """

    def read(self, size: int = -1, /) -> bytes:
        """
        Read up to `size` bytes (all of them, if negative).
        """
        ...


@runtime_checkable
class Writable(Protocol):
    """
    A stream that can be written to.
    """

    def write(self, data: Any, /) -> Any:
        """
        Write `data`.
        """
        ...


# Bytes in memory.
BytesLike = bytes | bytearray | memoryview

# What `parse` reads from: bytes, a path, or a readable binary stream.
Source = BytesLike | str | PathLike | Readable

# Where `build` writes to: nowhere (return the bytes), a path, or a writable stream.
Target = str | PathLike | Writable | None

# Byte order of numbers.
Endian = Literal["little", "big", "native"]

# Order of bits within a byte: "big" puts the first value in the most significant bits.
BitOrder = Literal["big", "little"]

# How many bits each value takes when packed.
NBits = Literal[1, 2, 4]

# Which side padding goes on.
Side = Literal["right", "left"]

# The `whence` of `io.IOBase.seek`: from the start, the current position, or the end.
Whence = Literal[0, 1, 2]

# A function of the context.
ContextFunction = Callable[[Context], Any]

# A number given directly, or computed from the context.
Dynamic = int | ContextFunction

# A condition given directly, or computed from the context.
Condition = bool | ContextFunction

# A key given directly, or computed from the context.
Key = Hashable | ContextFunction

# A function of a value and the context, such as `lambda value, ctx: value > 0`.
Predicate = Callable[[Any, Context], Any]
