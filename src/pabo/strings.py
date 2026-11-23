"""
String constructs.
"""

from dataclasses import dataclass
from typing import Literal

from pabo.base import Construct, readexact
from pabo.bytes import Bytes
from pabo.context import Dynamic, evaluate
from pabo.errors import PaboError, SizeofError, ValidationError
from pabo.numeric import Int
from pabo.wrappers import Prefixed


def _fragment(text: str, code: str) -> bytes:
    """
    Encode `text` as it appears in the middle of a string, i.e. without a BOM.
    """

    return ("a" + text).encode(code)[len("a".encode(code)) :]


def _decode(raw: bytes, code: str) -> str:
    try:
        return raw.decode(code)
    except UnicodeDecodeError as error:
        raise ValidationError(f"Cannot decode {raw!r} as {code}: {error}.") from error


def _readuntil(stream, terminator: bytes, unit: int) -> bytes:
    """
    Read whole code units until `terminator`, and return what came before it.
    """

    data = bytearray()
    while True:
        data += readexact(stream, unit)
        if data.endswith(terminator):
            return bytes(data[: -len(terminator)])


@dataclass
class CString(Construct[str]):
    """
    Represents a C-style (null-terminated) string.

    The terminator is one null code unit in the given encoding, so it is
    two bytes for UTF-16 and four bytes for UTF-32.
    """

    code: str = "utf-8"

    def _size(self, ctx):
        raise SizeofError("A CString has no fixed size.")

    def _build(self, data, stream, ctx):
        if "\x00" in data:
            raise ValidationError("A CString cannot contain a null character.")
        stream.write(data.encode(self.code) + _fragment("\x00", self.code))
        return data

    def _parse(self, stream, ctx):
        null = _fragment("\x00", self.code)
        return _decode(_readuntil(stream, null, len(null)), self.code)


@dataclass
class PascalString(Construct[str]):
    """
    Represents a Pascal-style string: its length in bytes, then the text.

    `pre` is the integer construct holding the length (such as `pb.u8`), and
    `code` the text encoding.
    """

    pre: Int
    code: str = "utf-8"

    def _size(self, ctx):
        raise SizeofError("A PascalString has no fixed size.")

    def _build(self, data, stream, ctx):
        Prefixed(self.pre, Bytes(-1))._build(data.encode(self.code), stream, ctx)
        return data

    def _parse(self, stream, ctx):
        return _decode(Prefixed(self.pre, Bytes(-1))._parse(stream, ctx), self.code)


Side = Literal["right", "left"]


@dataclass
class PaddedString(Construct[str]):
    """
    Represents a string padded to a fixed length in bytes.

    `pad` is the padding character (null by default), encoded like the rest
    of the string, so it is two bytes for UTF-16. With `side="right"` the
    padding follows the text; with `side="left"` it comes before it. Padding
    is stripped when parsing.
    """

    length: Dynamic
    code: str = "utf-8"
    pad: str = "\x00"
    side: Side = "right"

    def __post_init__(self):
        if len(self.pad) != 1:
            raise PaboError("The padding must be a single character.")
        if self.side not in ("right", "left"):
            raise PaboError(f"Invalid side {self.side!r}. Must be 'right' or 'left'.")

    def _size(self, ctx):
        return evaluate(self.length, ctx)

    def _build(self, data, stream, ctx):
        raw = data.encode(self.code)
        length = evaluate(self.length, ctx)
        if len(raw) > length:
            raise ValidationError(
                f"String too long: {len(raw)} bytes encoded, but only {length} available."
            )
        unit = _fragment(self.pad, self.code)
        missing = length - len(raw)
        padding = (unit * -(-missing // len(unit)))[:missing]
        stream.write(raw + padding if self.side == "right" else padding + raw)
        return data

    def _parse(self, stream, ctx):
        raw = readexact(stream, evaluate(self.length, ctx))
        unit = _fragment(self.pad, self.code)
        size = len(unit)
        if self.side == "right":
            raw = raw[: len(raw) - len(raw) % size]
            while raw.endswith(unit):
                raw = raw[:-size]
        else:
            raw = raw[len(raw) % size :]
            while raw.startswith(unit):
                raw = raw[size:]
        return _decode(raw, self.code)


@dataclass
class GreedyString(Construct[str]):
    """
    Represents a string running to the end of the stream.
    """

    code: str = "utf-8"

    def _size(self, ctx):
        raise SizeofError("A GreedyString has no fixed size.")

    def _build(self, data, stream, ctx):
        stream.write(data.encode(self.code))
        return data

    def _parse(self, stream, ctx):
        return _decode(stream.read(), self.code)


@dataclass
class Line(Construct[str]):
    """
    Represents a string ending with a CRLF (``\\r\\n``).
    """

    code: str = "utf-8"

    def _size(self, ctx):
        raise SizeofError("A Line has no fixed size.")

    def _build(self, data, stream, ctx):
        if "\r\n" in data:
            raise ValidationError("A Line cannot contain a CRLF.")
        stream.write(data.encode(self.code) + _fragment("\r\n", self.code))
        return data

    def _parse(self, stream, ctx):
        crlf = _fragment("\r\n", self.code)
        unit = len(_fragment("\x00", self.code))
        return _decode(_readuntil(stream, crlf, unit), self.code)
