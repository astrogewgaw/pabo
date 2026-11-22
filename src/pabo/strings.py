"""
String constructs.
"""

from dataclasses import dataclass

from pabo.base import Construct, read_exactly
from pabo.context import Dynamic, evaluate
from pabo.errors import SizeofError, ValidationError
from pabo.bytes import Bytes
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


def _read_until(stream, terminator: bytes, unit: int) -> bytes:
    """
    Read whole code units until `terminator`, and return what came before it.
    """

    data = bytearray()
    while True:
        data += read_exactly(stream, unit)
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
        return _decode(_read_until(stream, null, len(null)), self.code)


@dataclass
class PascalString(Construct[str]):
    """
    Represents a Pascal-style string.
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


@dataclass
class PaddedString(Construct[str]):
    """
    Represents a string padded by null bytes (\x00) to a fixed length.
    """

    length: Dynamic
    code: str = "utf-8"

    def _size(self, ctx):
        return evaluate(self.length, ctx)

    def _build(self, data, stream, ctx):
        raw = data.encode(self.code)
        length = evaluate(self.length, ctx)
        if len(raw) > length:
            raise ValidationError(
                f"String too long: {len(raw)} bytes encoded, but only {length} available."
            )
        stream.write(raw + b"\x00" * (length - len(raw)))
        return data

    def _parse(self, stream, ctx):
        raw = read_exactly(stream, evaluate(self.length, ctx))
        null = _fragment("\x00", self.code)
        unit = len(null)
        raw = raw[: len(raw) - len(raw) % unit]
        while raw.endswith(null):
            raw = raw[:-unit]
        return _decode(raw, self.code)


@dataclass
class Line(Construct[str]):
    """
    Represents a string ending with a CRLF (b'\r\n').
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
        return _decode(_read_until(stream, crlf, unit), self.code)
