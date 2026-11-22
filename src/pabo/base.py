"""
Base classes.
"""

import mmap
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from io import BytesIO
from pathlib import Path
from typing import Any, Generic, TypeVar

from pabo.context import Context
from pabo.errors import ContextError, PaboError, SizeofError, StreamError

T = TypeVar("T")


class Stop(Exception):
    """
    Raised by `StopIf` to end a `Specification` or `Sequential` early.
    """


def read_exactly(stream, size: int) -> bytes:
    """
    Read exactly `size` bytes from a stream, or raise a `StreamError`.
    """

    data = stream.read(size)
    if len(data) != size:
        raise StreamError(
            f"Stream ended early: expected {size} bytes, got {len(data)}."
        )
    return data


def tell(stream) -> int | None:
    """
    Return the stream position, or None if the stream cannot tell.
    """

    try:
        return stream.tell()
    except (AttributeError, OSError, ValueError):
        return None


@contextmanager
def scope(name: str, stream, docs: str = "") -> Generator[None, None, None]:
    """
    Add `name` to the path (and the start offset) of any `PaboError` raised inside.

    `docs` is recorded too, if no field further in already gave one.
    """

    start = tell(stream)
    try:
        yield
    except PaboError as error:
        error.path.insert(0, name)
        if error.offset is None:
            error.offset = start
        if docs and not error.docs:
            error.docs = docs
        raise


@dataclass
class Construct(ABC, Generic[T]):
    """
    Abstract base class for all binary constructs.

    When creating a new construct, implement three methods:

    - `_size(ctx)`: the size in bytes. Raise `SizeofError` if it is variable.
    - `_parse(stream, ctx)`: read the value from a binary stream and return it.
    - `_build(data, stream, ctx)`: write `data` to a binary stream, and return
      the value that was actually written (usually `data` itself).

    `ctx` is the `Context` holding the fields parsed or being built so far.
    Constructs that can be built without a value (constants, computed
    fields, ...) also override `_omittable` to return True. Look at the
    constructs in this package for inspiration.
    """

    docs: str = field(default="", kw_only=True, repr=False)

    @abstractmethod
    def _size(self, ctx: Context) -> int:
        pass

    @abstractmethod
    def _build(self, data: Any, stream, ctx: Context) -> Any:
        pass

    @abstractmethod
    def _parse(self, stream, ctx: Context) -> T:
        pass

    def _omittable(self) -> bool:
        """
        Whether a specification may build this field without being given a value.
        """

        return False

    def __truediv__(self, operand):
        if not isinstance(operand, str):
            raise PaboError(f"{operand!r} is not a str, so it cannot be used as docs.")
        return replace(self, docs=operand)

    def __floordiv__(self, operand):
        return self.__truediv__(operand)

    @property
    def size(self) -> int:
        """
        The size in bytes, if it can be known without any data.
        """

        return self.sizeof()

    def sizeof(self, ctx: dict | None = None) -> int:
        """
        The size in bytes, given the values in `ctx` (for example, parsed data).
        """

        try:
            size = self._size(Context(ctx or {}))
        except ContextError as error:
            raise SizeofError(
                f"The size depends on other fields: {error.msg}"
            ) from error
        if isinstance(size, int) and size >= 0:
            return size
        raise SizeofError(f"No reasonable size was returned (got {size!r}).")

    def build(self, data: Any, src=None, append: bool = False) -> bytes | None:
        """
        Build `data` into bytes.

        If `src` is None, the built bytes are returned. If `src` is a path, the
        file is overwritten (or appended to, if `append` is True). Otherwise,
        `src` should be a writable binary stream.
        """

        if src is None:
            stream = BytesIO()
            self._build(data, stream, Context())
            return stream.getvalue()
        if isinstance(src, (str, Path)):
            with open(src, "ab" if append else "wb") as f:
                self._build(data, f, Context())
            return None
        if hasattr(src, "write"):
            self._build(data, src, Context())
            return None
        raise PaboError(f"Cannot build into an object of type {type(src).__name__}.")

    def parse(self, dst) -> T:
        """
        Parse data from bytes, a path to a file, or a readable binary stream.

        Files given by path are memory-mapped, so large arrays are read without
        copying (the arrays returned are read-only views of the file), and lazy
        fields can still be read after `parse` returns.
        """

        if isinstance(dst, (bytes, bytearray, memoryview)):
            return self._parse(BytesIO(dst), Context())
        if isinstance(dst, (str, Path)):
            with open(dst, "rb") as f:
                try:
                    stream = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                except (OSError, ValueError):
                    return self._parse(f, Context())
            return self._parse(stream, Context())
        if hasattr(dst, "read"):
            return self._parse(dst, Context())
        raise PaboError(f"Cannot parse from an object of type {type(dst).__name__}.")
