"""
Constructs that move around the stream: seeking, peeking, alignment and laziness.
"""

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pabo.base import Construct, readexact, tell
from pabo.context import Context, evaluate
from pabo.errors import PaboError, SizeofError, StreamError
from pabo.hints import Dynamic, Endian, Whence
from pabo.specify import Specification


def _offset(value, ctx) -> int:
    offset = evaluate(value, ctx)
    if not isinstance(offset, int):
        raise PaboError(f"THE OFFSET MUST BE AN INTEGER, GOT {offset!r}.")
    return offset


def _checkwhence(whence) -> None:
    if whence not in (0, 1, 2):
        raise PaboError(f"INVALID WHENCE {whence!r}. MUST BE 0, 1 OR 2.")


def _seek(stream, offset: int, whence: int = 0) -> int:
    try:
        stream.seek(offset, whence)
        return stream.tell()
    except (AttributeError, OSError, ValueError) as error:
        raise StreamError(
            f"CANNOT SEEK TO {offset} (whence={whence}): {error}."
        ) from error


@dataclass
class Seek(Construct[int]):
    """
    Move the stream to `offset` (relative to `whence`, as in `io.IOBase.seek`).

    Parses and builds the new position. Takes no value when building.
    """

    offset: Dynamic
    whence: Whence = 0

    def __post_init__(self):
        _checkwhence(self.whence)

    def _omittable(self):
        return True

    def _size(self, ctx):
        raise SizeofError("A SEEK HAS NO MEANINGFUL SIZE.")

    def _build(self, data, stream, ctx):
        return _seek(stream, _offset(self.offset, ctx), self.whence)

    def _parse(self, stream, ctx):
        return _seek(stream, _offset(self.offset, ctx), self.whence)


@dataclass
class Tell(Construct[int]):
    """
    The current stream position. Takes no bytes and no value when building.
    """

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _position(self, stream) -> int:
        position = tell(stream)
        if position is None:
            raise StreamError("THE STREAM CANNOT TELL ITS POSITION.")
        return position

    def _build(self, data, stream, ctx):
        return self._position(stream)

    def _parse(self, stream, ctx):
        return self._position(stream)


@dataclass
class Pointer(Construct):
    """
    Parse/build `wraps` at `offset`, then return to where the stream was.

    Takes no space where it appears, since the data lives elsewhere.
    """

    offset: Dynamic
    wraps: Construct
    whence: Whence = 0

    def __post_init__(self):
        _checkwhence(self.whence)

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        return 0

    def _build(self, data, stream, ctx):
        back = stream.tell()
        _seek(stream, _offset(self.offset, ctx), self.whence)
        try:
            return self.wraps._build(data, stream, ctx)
        finally:
            stream.seek(back)

    def _parse(self, stream, ctx):
        back = stream.tell()
        _seek(stream, _offset(self.offset, ctx), self.whence)
        try:
            return self.wraps._parse(stream, ctx)
        finally:
            stream.seek(back)


@dataclass
class Peek(Construct):
    """
    Parse `wraps` without moving the stream (look ahead). Builds nothing.
    """

    wraps: Construct

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _build(self, data, stream, ctx):
        return data

    def _parse(self, stream, ctx):
        back = stream.tell()
        try:
            return self.wraps._parse(stream, ctx)
        finally:
            stream.seek(back)


@dataclass
class Aligned(Construct):
    """
    Pad `wraps` with `fill` bytes up to the next multiple of `modulus` bytes.
    """

    modulus: int
    wraps: Construct
    fill: bytes = b"\x00"

    def __post_init__(self):
        if self.modulus < 1:
            raise PaboError("THE MODULUS MUST BE POSITIVE.")
        if len(self.fill) != 1:
            raise PaboError("THE FILL MUST BE A SINGLE BYTE.")

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        size = self.wraps._size(ctx)
        return size + (-size % self.modulus)

    def _build(self, data, stream, ctx):
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        raw = buffer.getvalue()
        stream.write(raw + self.fill * (-len(raw) % self.modulus))
        return built

    def _parse(self, stream, ctx):
        start = stream.tell()
        data = self.wraps._parse(stream, ctx)
        readexact(stream, -(stream.tell() - start) % self.modulus)
        return data


def AlignedSpec(
    modulus: int, fields: dict[str, Construct], endian: Endian | None = None
) -> Specification:
    """
    A specification with every field aligned to a multiple of `modulus` bytes.
    """

    return Specification(
        {name: Aligned(modulus, member) for name, member in fields.items()},
        endian=endian,
    )


class LazyValue:
    """
    A value that is parsed from the stream the first time it is asked for.

    Call `get()` (or read `value`) to parse it. The stream must still be open
    then: files parsed from a path are memory-mapped, so they stay readable.
    """

    def __init__(self, construct: Construct, stream, offset: int, ctx: Context):
        self._construct = construct
        self._stream = stream
        self._offset = offset
        self._ctx = ctx
        self._parsed = False
        self._value: Any = None

    @property
    def offset(self) -> int:
        """
        Where the value starts in the stream.
        """

        return self._offset

    def get(self) -> Any:
        """
        Parse (once) and return the value.
        """

        if not self._parsed:
            back = self._stream.tell()
            self._stream.seek(self._offset)
            try:
                self._value = self._construct._parse(self._stream, self._ctx)
            finally:
                self._stream.seek(back)
            self._parsed = True
        return self._value

    @property
    def value(self) -> Any:
        """
        The parsed value (the same as `get()`).
        """

        return self.get()

    def __repr__(self) -> str:
        state = repr(self._value) if self._parsed else "not parsed yet"
        return f"LazyValue({state}, offset={self._offset})"


@dataclass
class Lazy(Construct):
    """
    Skip over `wraps` when parsing, and return a `LazyValue` that parses it on demand.

    `wraps` must have a size that is known when it is reached (it may depend
    on earlier fields). Building accepts a `LazyValue` or a plain value.
    """

    wraps: Construct

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        if isinstance(data, LazyValue):
            data = data.get()
        return self.wraps._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        offset = stream.tell()
        size = self.wraps._size(ctx)
        end = _seek(stream, 0, 2)
        stream.seek(offset)
        if end - offset < size:
            raise StreamError(
                f"STREAM ENDED EARLY: EXPECTED {size} BYTES, GOT {end - offset}."
            )
        stream.seek(offset + size)
        return LazyValue(self.wraps, stream, offset, ctx)
