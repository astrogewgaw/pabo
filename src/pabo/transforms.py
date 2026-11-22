"""
Transforms: compressed, encoded and checksummed data.
"""

import bz2
import gzip
import hashlib
import lzma
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pabo.base import Construct, read_exactly
from pabo.context import Dynamic, evaluate
from pabo.errors import PaboError, SizeofError, ValidationError

CODECS: dict[str, tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]] = {
    "zlib": (zlib.decompress, zlib.compress),
    "gzip": (gzip.decompress, gzip.compress),
    "bz2": (bz2.decompress, bz2.compress),
    "lzma": (lzma.decompress, lzma.compress),
}


@dataclass
class Transformed(Construct):
    """
    Parse `wraps` from bytes that are decoded first (an encoded sub-stream).

    `length` bytes are read (all the rest of the stream if negative, the
    default), passed through `decode`, and `wraps` is parsed from the result.
    Building runs `encode` over the bytes built by `wraps`. When `length` is
    negative, put this last, or inside a `Prefixed`, so it knows where to stop.
    """

    wraps: Construct
    decode: Callable[[bytes], bytes]
    encode: Callable[[bytes], bytes]
    length: Dynamic = -1

    def _size(self, ctx):
        size = evaluate(self.length, ctx)
        if size < 0:
            raise SizeofError(
                "A Transformed construct without a length has no fixed size."
            )
        return size

    def _build(self, data, stream, ctx):
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        try:
            raw = self.encode(buffer.getvalue())
        except Exception as error:
            raise ValidationError(f"Cannot encode the data: {error}.") from error
        size = evaluate(self.length, ctx)
        if size >= 0 and len(raw) != size:
            raise ValidationError(f"Expected {size} encoded bytes, got {len(raw)}.")
        stream.write(raw)
        return built

    def _parse(self, stream, ctx):
        size = evaluate(self.length, ctx)
        raw = read_exactly(stream, size) if size >= 0 else stream.read()
        try:
            decoded = self.decode(raw)
        except Exception as error:
            raise ValidationError(f"Cannot decode the data: {error}.") from error
        return self.wraps._parse(BytesIO(decoded), ctx)


def Compressed(
    wraps: Construct, codec: str = "zlib", length: Dynamic = -1
) -> Transformed:
    """
    `wraps`, compressed with "zlib", "gzip", "bz2" or "lzma".

    Like `Transformed`, it reads `length` bytes, or the rest of the stream.
    """

    if codec not in CODECS:
        raise PaboError(f"Unknown codec {codec!r}. Must be one of {list(CODECS)}.")
    decode, encode = CODECS[codec]
    return Transformed(wraps, decode, encode, length)


def _hasher(algorithm: str | Callable[[bytes], Any]) -> Callable[[bytes], Any]:
    if callable(algorithm):
        return algorithm
    if algorithm == "crc32":
        return zlib.crc32
    if algorithm == "adler32":
        return zlib.adler32
    if algorithm in hashlib.algorithms_available:
        return lambda raw: hashlib.new(algorithm, raw).digest()
    raise PaboError(
        f"Unknown checksum {algorithm!r}. Use 'crc32', 'adler32', a hashlib name or a function."
    )


@dataclass
class Checksummed(Construct):
    """
    `wraps`, followed by a checksum of its bytes stored as `check`.

    `algorithm` is "crc32" or "adler32" (giving ints, so use an `Int(4)`), a
    hashlib name such as "md5" or "sha256" (giving digest bytes, so use a
    `Bytes`), or a function from bytes to the checksum. Parsing checks the
    checksum and returns the value of `wraps`; building computes it.
    """

    wraps: Construct
    check: Construct
    algorithm: Any = "crc32"

    def __post_init__(self):
        _hasher(self.algorithm)

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        return self.wraps._size(ctx) + self.check._size(ctx)

    def _build(self, data, stream, ctx):
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        raw = buffer.getvalue()
        stream.write(raw)
        self.check._build(_hasher(self.algorithm)(raw), stream, ctx)
        return built

    def _parse(self, stream, ctx):
        start = stream.tell()
        value = self.wraps._parse(stream, ctx)
        end = stream.tell()
        stream.seek(start)
        raw = read_exactly(stream, end - start)
        stored = self.check._parse(stream, ctx)
        computed = _hasher(self.algorithm)(raw)
        if stored != computed:
            raise ValidationError(
                f"Checksum mismatch: stored {stored!r}, computed {computed!r}."
            )
        return value
