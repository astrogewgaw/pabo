"""
Base classes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any


class PaboError(Exception):
    """
    Base class for all errors in pabo.
    """

    def __init__(self, msg: str):
        super().__init__(f"바보! {msg} ABORT.")


def read_exactly(stream, size: int) -> bytes:
    """
    Read exactly `size` bytes from a stream, or raise a `PaboError`.
    """

    data = stream.read(size)
    if len(data) != size:
        raise PaboError(
            f"PREMATURE END OF STREAM: EXPECTED {size} BYTES, GOT {len(data)}."
        )
    return data


@dataclass
class Construct(ABC):
    """
    Abstract base class for all binary constructs.

    This class implements the basic functionality required by all binary
    constructs. When creating a new construct, the user has to implement
    just 3 methods: `_size`, `_parse`, and `_build`. The user may look at
    the constructs already implemented in this package for inspiration.
    """

    docs: str = field(default="", kw_only=True, repr=False)

    @abstractmethod
    def _size(self) -> int:
        pass

    @abstractmethod
    def _build(self, data, stream) -> None:
        pass

    @abstractmethod
    def _parse(self, stream) -> Any:
        pass

    def __truediv__(self, operand):
        if not isinstance(operand, str):
            raise PaboError(f"{operand} not a str. Cannot be used as docs.")
        self.docs = operand
        return self

    def __floordiv__(self, operand):
        return self.__truediv__(operand)

    @property
    def size(self) -> int:
        size = self._size()
        if isinstance(size, int) and size >= 0:
            return size
        raise PaboError("No reasonable size was returned.")

    def build(self, data, src=None, append: bool = False) -> bytes | None:
        """
        Build `data` into bytes.

        If `src` is None, the built bytes are returned. If `src` is a path, the
        file is overwritten (or appended to, if `append` is True). Otherwise,
        `src` should be a writable binary stream.
        """

        if src is None:
            stream = BytesIO()
            self._build(data, stream)
            return stream.getvalue()
        if isinstance(src, (str, Path)):
            with open(src, "ab" if append else "wb") as f:
                self._build(data, f)
            return None
        if hasattr(src, "write"):
            self._build(data, src)
            return None
        raise PaboError(f"Cannot build into an object of type {type(src).__name__}.")

    def parse(self, dst) -> Any:
        """
        Parse data from bytes, a path to a file, or a readable binary stream.
        """

        if isinstance(dst, (bytes, bytearray, memoryview)):
            return self._parse(BytesIO(dst))
        if isinstance(dst, (str, Path)):
            with open(dst, "rb") as f:
                return self._parse(f)
        if hasattr(dst, "read"):
            return self._parse(dst)
        raise PaboError(f"Cannot parse from an object of type {type(dst).__name__}.")
