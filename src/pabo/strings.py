"""
String constructs.
"""

from dataclasses import dataclass

from pabo.base import Construct, PaboError, read_exactly
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
        raise PaboError(f"Cannot decode {raw!r} as {code}: {error}.") from error


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
class CString(Construct):
    """
    Represents a C-style (null-terminated) string.

    The terminator is one null code unit in the given encoding, so it is
    two bytes for UTF-16 and four bytes for UTF-32.
    """

    code: str = "utf-8"

    def _size(self):
        raise PaboError("A CString has no fixed size.")

    def _build(self, data, stream) -> None:
        if "\x00" in data:
            raise PaboError("A CString cannot contain a null character.")
        stream.write(data.encode(self.code) + _fragment("\x00", self.code))

    def _parse(self, stream):
        null = _fragment("\x00", self.code)
        return _decode(_read_until(stream, null, len(null)), self.code)


@dataclass
class PascalString(Construct):
    """
    Represents a Pascal-style string.
    """

    pre: Int
    code: str = "utf-8"

    def _size(self):
        raise PaboError("A PascalString has no fixed size.")

    def _build(self, data, stream) -> None:
        Prefixed(self.pre, Bytes(-1))._build(data.encode(self.code), stream)

    def _parse(self, stream):
        return _decode(Prefixed(self.pre, Bytes(-1))._parse(stream), self.code)


@dataclass
class PaddedString(Construct):
    """
    Represents a string padded by null bytes (\x00) to a fixed length.
    """

    length: int
    code: str = "utf-8"

    def _size(self):
        return self.length

    def _build(self, data, stream) -> None:
        raw = data.encode(self.code)
        if len(raw) > self.length:
            raise PaboError(
                f"String too long: {len(raw)} bytes encoded, but only {self.length} available."
            )
        stream.write(raw + b"\x00" * (self.length - len(raw)))

    def _parse(self, stream):
        raw = read_exactly(stream, self.length)
        null = _fragment("\x00", self.code)
        unit = len(null)
        raw = raw[: len(raw) - len(raw) % unit]
        while raw.endswith(null):
            raw = raw[:-unit]
        return _decode(raw, self.code)


@dataclass
class Line(Construct):
    """
    Represents a string ending with a CRLF (b'\r\n').
    """

    code: str = "utf-8"

    def _size(self):
        raise PaboError("A Line has no fixed size.")

    def _build(self, data, stream):
        if "\r\n" in data:
            raise PaboError("A Line cannot contain a CRLF.")
        stream.write(data.encode(self.code) + _fragment("\r\n", self.code))

    def _parse(self, stream):
        crlf = _fragment("\r\n", self.code)
        unit = len(_fragment("\x00", self.code))
        return _decode(_read_until(stream, crlf, unit), self.code)
