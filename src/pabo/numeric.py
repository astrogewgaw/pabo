"""
Numerical constructs.
"""

import mmap
import struct
import sys
from dataclasses import dataclass
from typing import Literal

import numpy as np

from pabo.base import Construct, read_exactly
from pabo.context import Context, Dynamic, evaluate
from pabo.errors import PaboError, SizeofError, StreamError, ValidationError
from pabo.packing import BitOrder, pack_bits, unpack_bits

Endian = Literal["little", "big", "native"]

ENDIANS = {"little": "<", "big": ">", "native": "="}
INT_CODES = {1: "b", 2: "h", 4: "i", 8: "q"}
FLOAT_CODES = {2: "e", 4: "f", 8: "d"}


def _check_endian(endian: str | None) -> None:
    if endian is not None and endian not in ENDIANS:
        raise PaboError(
            f"Invalid endianness {endian!r}. Must be one of {list(ENDIANS)}."
        )


def _check_bitorder(bitorder: str) -> None:
    if bitorder not in ("big", "little"):
        raise PaboError(f"Invalid bit order {bitorder!r}. Must be 'big' or 'little'.")


def resolve_endian(endian: str | None, ctx: Context) -> str:
    """
    Return `endian`, or the default set by an enclosing specification, or "little".
    """

    return endian or ctx.setting("_endian") or "little"


class _Fixed(Construct):
    """
    Shared implementation for fixed-width numbers.

    If `endian` is None, the default of the enclosing specification is used
    (little-endian if there is none).
    """

    width: int
    endian: "Endian | None"

    def format_for(self, endian: str) -> str:
        """
        The `struct` format for the given endianness.
        """

        raise NotImplementedError

    @property
    def format(self) -> str:
        """
        The `struct` format (little-endian if no endianness was given).
        """

        return self.format_for(self.endian or "little")

    def _size(self, ctx):
        return self.width

    def _build(self, data, stream, ctx):
        fmt = self.format_for(resolve_endian(self.endian, ctx))
        try:
            stream.write(struct.pack(fmt, data))
        except struct.error as error:
            raise ValidationError(
                f"Cannot build {data!r} as {self!r}: {error}."
            ) from error
        return data

    def _parse(self, stream, ctx):
        fmt = self.format_for(resolve_endian(self.endian, ctx))
        return struct.unpack(fmt, read_exactly(stream, self.width))[0]


@dataclass
class Int(_Fixed):
    """
    Represents a fixed-width integer, of any whole number of bytes.

    Widths of 1, 2, 4 and 8 bytes use `struct`; any other width (3, 16, ...)
    uses `int.from_bytes`.
    """

    width: int
    signed: bool = False
    endian: Endian | None = None

    def __post_init__(self):
        if self.width < 1:
            raise PaboError(
                f"Unsupported integer width {self.width}. Must be positive."
            )
        _check_endian(self.endian)

    def format_for(self, endian: str) -> str:
        """
        The `struct` format for the given endianness (only for 1, 2, 4 or 8 bytes).
        """

        if self.width not in INT_CODES:
            raise PaboError(
                f"There is no struct format for {self.width}-byte integers."
            )
        code = INT_CODES[self.width]
        return ENDIANS[endian] + (code if self.signed else code.upper())

    def _byteorder(self, ctx) -> Literal["little", "big"]:
        endian = resolve_endian(self.endian, ctx)
        if endian == "native":
            return sys.byteorder
        return "big" if endian == "big" else "little"

    def _build(self, data, stream, ctx):
        if self.width in INT_CODES:
            return super()._build(data, stream, ctx)
        try:
            raw = data.to_bytes(self.width, self._byteorder(ctx), signed=self.signed)
        except (AttributeError, OverflowError) as error:
            raise ValidationError(
                f"Cannot build {data!r} as {self!r}: {error}."
            ) from error
        stream.write(raw)
        return data

    def _parse(self, stream, ctx):
        if self.width in INT_CODES:
            return super()._parse(stream, ctx)
        raw = read_exactly(stream, self.width)
        return int.from_bytes(raw, self._byteorder(ctx), signed=self.signed)


@dataclass
class Float(_Fixed):
    """
    Represents a fixed-width floating point number (2, 4 or 8 bytes).
    """

    width: int
    endian: Endian | None = None

    def __post_init__(self):
        if self.width not in FLOAT_CODES:
            raise PaboError(
                f"Unsupported float width {self.width}. Must be one of {list(FLOAT_CODES)}."
            )
        _check_endian(self.endian)

    def format_for(self, endian: str) -> str:
        """
        The `struct` format for the given endianness.
        """

        return ENDIANS[endian] + FLOAT_CODES[self.width]


@dataclass
class VarInt(Construct[int]):
    """
    Represents an unsigned variable-length integer (LEB128, as in protobuf).

    Each byte holds 7 bits of the value, least significant first, and its
    top bit is set when more bytes follow.
    """

    def _size(self, ctx):
        raise SizeofError("A VarInt has no fixed size.")

    def _build(self, data, stream, ctx):
        if not isinstance(data, int) or data < 0:
            raise ValidationError(f"A VarInt must be a non-negative int, got {data!r}.")
        value, out = data, bytearray()
        while True:
            byte, value = value & 0x7F, value >> 7
            out.append(byte | (0x80 if value else 0))
            if not value:
                break
        stream.write(bytes(out))
        return data

    def _parse(self, stream, ctx):
        value = shift = 0
        while True:
            byte = read_exactly(stream, 1)[0]
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value


@dataclass
class ZigZag(Construct[int]):
    """
    Represents a signed variable-length integer (ZigZag-encoded LEB128).

    0, -1, 1, -2, ... are stored as the VarInts 0, 1, 2, 3, ...
    """

    def _size(self, ctx):
        raise SizeofError("A ZigZag integer has no fixed size.")

    def _build(self, data, stream, ctx):
        if not isinstance(data, int):
            raise ValidationError(f"A ZigZag integer must be an int, got {data!r}.")
        VarInt()._build(2 * data if data >= 0 else -2 * data - 1, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        value = VarInt()._parse(stream, ctx)
        return value >> 1 if not value & 1 else -((value + 1) >> 1)


@dataclass
class Array(Construct):
    """
    Represents an array of fixed-width numbers.

    A negative `count` reads until the end of the stream. If `packing` is set
    (any number of bits from 1 up to the width of `dtype`), each element is
    stored in that many bits, `bitorder` decides whether the first element sits
    in the most ("big") or least ("little") significant bits of each byte, and
    the values are returned as `dtype`. Packings of 1, 2 and 4 bits use the
    fast C++ extension. See `pabo.packing` for the exact layout.
    """

    dtype: Int | Float
    count: Dynamic = -1
    packing: int | None = None
    bitorder: BitOrder = "big"

    def __post_init__(self):
        if isinstance(self.dtype, Int) and self.dtype.width not in INT_CODES:
            raise PaboError("Array elements must be 1, 2, 4 or 8 bytes wide.")
        if self.packing is not None:
            if not isinstance(self.dtype, Int):
                raise PaboError("Only integer arrays can be packed.")
            if not 1 <= self.packing <= 8 * self.dtype.width:
                raise PaboError(
                    f"Unsupported packing {self.packing}. Must be from 1 to "
                    f"{8 * self.dtype.width} bits for {self.dtype.width}-byte elements."
                )
        _check_bitorder(self.bitorder)

    @property
    def numpy_dtype(self) -> np.dtype:
        """
        The numpy dtype of the elements (little-endian if no endianness was given).
        """

        return np.dtype(self.dtype.format)

    def dtype_for(self, ctx) -> np.dtype:
        """
        The numpy dtype of the elements, with the endianness resolved from `ctx`.
        """

        return np.dtype(self.dtype.format_for(resolve_endian(self.dtype.endian, ctx)))

    def _nbytes(self, count: int) -> int:
        if self.packing is None:
            return count * self.dtype.width
        return -(-count * self.packing // 8)

    def _parse_mapped(
        self, stream: mmap.mmap, count: int, dtype: np.dtype
    ) -> np.ndarray:
        """
        Return a read-only view of the memory-mapped file, without copying.
        """

        start = stream.tell()
        available = len(stream) - start
        nbytes = self._nbytes(count) if count >= 0 else available
        if nbytes > available:
            raise StreamError(
                f"Stream ended early: expected {nbytes} bytes, got {available}."
            )
        if nbytes % dtype.itemsize:
            raise StreamError(
                f"{nbytes} bytes is not a whole number of {dtype.itemsize}-byte elements."
            )
        array = np.frombuffer(
            stream, dtype=dtype, count=nbytes // dtype.itemsize, offset=start
        )
        stream.seek(start + nbytes)
        return array

    def _parse_into(self, stream, count: int, dtype: np.dtype) -> np.ndarray:
        """
        Read straight into a new array, without an intermediate bytes object.
        """

        array = np.empty(count, dtype=dtype)
        view = memoryview(array.view(np.uint8))
        nbytes, got = view.nbytes, 0
        while got < nbytes:
            n = stream.readinto(view[got:])
            if not n:
                raise StreamError(
                    f"Stream ended early: expected {nbytes} bytes, got {got}."
                )
            got += n
        return array

    def _count(self, ctx) -> int:
        count = evaluate(self.count, ctx)
        if not isinstance(count, (int, np.integer)):
            raise PaboError(f"The count must be an integer, got {count!r}.")
        return int(count)

    def _size(self, ctx):
        count = self._count(ctx)
        if count < 0:
            raise SizeofError("A greedy array has no fixed size.")
        return self._nbytes(count)

    def _build(self, data, stream, ctx):
        dtype = self.dtype_for(ctx)
        try:
            array = np.asarray(data, dtype=dtype).ravel()
        except (OverflowError, TypeError, ValueError) as error:
            raise ValidationError(
                f"Cannot build {data!r} as {dtype} values: {error}."
            ) from error
        count = self._count(ctx)
        if count >= 0:
            if array.size < count:
                raise ValidationError(
                    f"Not enough data to build: need {count} elements, got {array.size}."
                )
            array = array[:count]
        if self.packing is None:
            stream.write(array.tobytes())
            return array
        try:
            stream.write(pack_bits(array, self.packing, self.bitorder))
        except PaboError as error:
            raise ValidationError(error.msg) from None
        return array

    def _parse(self, stream, ctx):
        count = self._count(ctx)
        if self.packing is None and isinstance(stream, mmap.mmap):
            return self._parse_mapped(stream, count, self.dtype_for(ctx))
        if self.packing is None and count >= 0 and hasattr(stream, "readinto"):
            return self._parse_into(stream, count, self.dtype_for(ctx))
        raw = read_exactly(stream, self._nbytes(count)) if count >= 0 else stream.read()
        if self.packing is None:
            if len(raw) % self.dtype.width:
                raise StreamError(
                    f"{len(raw)} bytes is not a whole number of "
                    f"{self.dtype.width}-byte elements."
                )
            return np.frombuffer(raw, dtype=self.dtype_for(ctx))
        values = unpack_bits(raw, self.packing, self.bitorder)
        if count >= 0:
            values = values[:count]
        return values.astype(self.dtype_for(ctx))
