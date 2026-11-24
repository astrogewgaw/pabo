"""
Numerical constructs.
"""

import mmap
import struct
import sys
from dataclasses import dataclass
from typing import Literal

import numpy as np

from pabo.base import Construct, T, buffer, readexact
from pabo.context import Context
from pabo.errors import PaboError, SizeofError, StreamError, ValidationError
from pabo.expressions import evaluate
from pabo.hints import BitOrder, Dynamic, Endian, NBits
from pabo.packing import WIDTHS, packbits, unpackbits

ENDIANS = {"little": "<", "big": ">", "native": "="}
INT_CODES = {1: "b", 2: "h", 4: "i", 8: "q"}
FLOAT_CODES = {2: "e", 4: "f", 8: "d"}


def _checkendian(endian: str | None) -> None:
    if endian is not None and endian not in ENDIANS:
        raise PaboError(
            f"INVALID ENDIANNESS {endian!r}. MUST BE ONE OF {list(ENDIANS)}."
        )


def _checkbitorder(bitorder: str) -> None:
    if bitorder not in ("big", "little"):
        raise PaboError(f"INVALID BIT ORDER {bitorder!r}. MUST BE 'big' OR 'little'.")


def resolveendian(endian: Endian | None, ctx: Context) -> Endian:
    """
    Return `endian`, or the default set by an enclosing specification, or "little".
    """

    return endian or ctx.setting("_endian") or "little"


class _Fixed(Construct[T]):
    """
    Shared implementation for fixed-width numbers.

    If `endian` is None, the default of the enclosing specification is used
    (little-endian if there is none).
    """

    width: int
    endian: "Endian | None"

    def formatfor(self, endian: Endian) -> str:
        """
        The `struct` format for the given endianness.
        """

        raise NotImplementedError

    @property
    def format(self) -> str:
        """
        The `struct` format (little-endian if no endianness was given).
        """

        return self.formatfor(self.endian or "little")

    def _size(self, ctx):
        return self.width

    def _build(self, data, stream, ctx):
        fmt = self.formatfor(resolveendian(self.endian, ctx))
        try:
            stream.write(struct.pack(fmt, data))
        except struct.error as error:
            raise ValidationError(
                f"CANNOT BUILD {data!r} AS {self!r}: {error}."
            ) from error
        return data

    def _parse(self, stream, ctx):
        fmt = self.formatfor(resolveendian(self.endian, ctx))
        return struct.unpack(fmt, readexact(stream, self.width))[0]


@dataclass
class Int(_Fixed[int]):
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
                f"UNSUPPORTED INTEGER WIDTH {self.width}. MUST BE POSITIVE."
            )
        _checkendian(self.endian)

    def formatfor(self, endian: Endian) -> str:
        """
        The `struct` format for the given endianness (only for 1, 2, 4 or 8 bytes).
        """

        if self.width not in INT_CODES:
            raise PaboError(
                f"THERE IS NO STRUCT FORMAT FOR {self.width}-BYTE INTEGERS."
            )
        code = INT_CODES[self.width]
        return ENDIANS[endian] + (code if self.signed else code.upper())

    def _byteorder(self, ctx) -> Literal["little", "big"]:
        endian = resolveendian(self.endian, ctx)
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
                f"CANNOT BUILD {data!r} AS {self!r}: {error}."
            ) from error
        stream.write(raw)
        return data

    def _parse(self, stream, ctx):
        if self.width in INT_CODES:
            return super()._parse(stream, ctx)
        raw = readexact(stream, self.width)
        return int.from_bytes(raw, self._byteorder(ctx), signed=self.signed)


@dataclass
class Float(_Fixed[float]):
    """
    Represents a fixed-width floating point number (2, 4 or 8 bytes).
    """

    width: int
    endian: Endian | None = None

    def __post_init__(self):
        if self.width not in FLOAT_CODES:
            raise PaboError(
                f"UNSUPPORTED FLOAT WIDTH {self.width}. MUST BE ONE OF {list(FLOAT_CODES)}."
            )
        _checkendian(self.endian)

    def formatfor(self, endian: Endian) -> str:
        """
        The `struct` format for the given endianness.
        """

        return ENDIANS[endian] + FLOAT_CODES[self.width]


@dataclass
class VarInt(Construct[int]):
    """
    Represents an unsigned variable-length integer.

    Each byte holds 7 bits of the value, and its top bit is set when more bytes
    follow. With `order="little"` (the default) the least significant 7 bits come
    first, as in LEB128, protobuf and DWARF. With `order="big"` the most
    significant come first, as in MIDI's variable-length quantities. Unlike
    `Int`, the order is not taken from the enclosing specification, since it is
    part of the format rather than of the machine.
    """

    order: Literal["little", "big"] = "little"

    def __post_init__(self):
        if self.order not in ("little", "big"):
            raise PaboError(f"UNKNOWN ORDER {self.order!r}. MUST BE 'little' OR 'big'.")

    def _size(self, ctx):
        raise SizeofError("A VarInt HAS NO FIXED SIZE.")

    def _build(self, data, stream, ctx):
        if not isinstance(data, int) or data < 0:
            raise ValidationError(f"A VarInt MUST BE A NON-NEGATIVE INT, GOT {data!r}.")
        groups, value = [data & 0x7F], data >> 7
        while value:
            groups.append(value & 0x7F)
            value >>= 7
        if self.order == "big":
            groups.reverse()
        last = len(groups) - 1
        stream.write(
            bytes(g | (0x80 if ix < last else 0) for ix, g in enumerate(groups))
        )
        return data

    def _parse(self, stream, ctx):
        value = shift = 0
        big = self.order == "big"
        while True:
            byte = readexact(stream, 1)[0]
            if big:
                value = (value << 7) | (byte & 0x7F)
            else:
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
        raise SizeofError("A ZigZag INTEGER HAS NO FIXED SIZE.")

    def _build(self, data, stream, ctx):
        if not isinstance(data, int):
            raise ValidationError(f"A ZigZag INTEGER MUST BE AN INT, GOT {data!r}.")
        VarInt()._build(2 * data if data >= 0 else -2 * data - 1, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        value = VarInt()._parse(stream, ctx)
        return value >> 1 if not value & 1 else -((value + 1) >> 1)


@dataclass
class Array(Construct[np.ndarray]):
    """
    Represents an array of fixed-width numbers.

    A negative `count` reads until the end of the stream. If `packing` is set
    (1, 2 or 4 bits), each element is stored in that many bits, `bitorder`
    decides whether the first element sits in the most ("big") or least
    ("little") significant bits of each byte, and the values are returned as
    `dtype`. Packing uses the C++ extension; see `pabo.packing` for the layout.

    Like `np.frombuffer`, parsing bytes in memory (or a memory-mapped file)
    returns a read-only view of them, not a copy; call `.copy()` on it for an
    array you can change. Packed arrays, and arrays read from other streams,
    are new arrays.
    """

    dtype: Int | Float
    count: Dynamic = -1
    packing: NBits | None = None
    bitorder: BitOrder = "big"

    def __post_init__(self):
        if isinstance(self.dtype, Int) and self.dtype.width not in INT_CODES:
            raise PaboError("ARRAY ELEMENTS MUST BE 1, 2, 4 OR 8 BYTES WIDE.")
        if self.packing is not None:
            if not isinstance(self.dtype, Int):
                raise PaboError("ONLY INTEGER ARRAYS CAN BE PACKED.")
            if self.packing not in WIDTHS:
                raise PaboError(
                    f"UNSUPPORTED PACKING {self.packing}. MUST BE 1, 2 OR 4 BITS."
                )
        _checkbitorder(self.bitorder)

    @property
    def numpydtype(self) -> np.dtype:
        """
        The numpy dtype of the elements (little-endian if no endianness was given).
        """

        return np.dtype(self.dtype.format)

    def dtypefor(self, ctx) -> np.dtype:
        """
        The numpy dtype of the elements, with the endianness resolved from `ctx`.
        """

        return np.dtype(self.dtype.formatfor(resolveendian(self.dtype.endian, ctx)))

    def _nbytes(self, count: int) -> int:
        if self.packing is None:
            return count * self.dtype.width
        return -(-count * self.packing // 8)

    def _parseview(
        self, stream, memory: "mmap.mmap | memoryview", count: int, dtype: np.dtype
    ) -> np.ndarray:
        """
        Return a read-only view of the memory behind the stream, without copying.
        """

        start = stream.tell()
        available = len(memory) - start
        nbytes = self._nbytes(count) if count >= 0 else available
        if nbytes > available:
            raise StreamError(
                f"STREAM ENDED EARLY: EXPECTED {nbytes} BYTES, GOT {available}."
            )
        if nbytes % dtype.itemsize:
            raise StreamError(
                f"{nbytes} BYTES IS NOT A WHOLE NUMBER OF {dtype.itemsize}-BYTE ELEMENTS."
            )
        array = np.frombuffer(
            memory, dtype=dtype, count=nbytes // dtype.itemsize, offset=start
        )
        array.flags.writeable = False
        stream.seek(start + nbytes)
        return array

    def _parseinto(self, stream, count: int, dtype: np.dtype) -> np.ndarray:
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
                    f"STREAM ENDED EARLY: EXPECTED {nbytes} BYTES, GOT {got}."
                )
            got += n
        return array

    def _count(self, ctx) -> int:
        count = evaluate(self.count, ctx)
        if not isinstance(count, (int, np.integer)):
            raise PaboError(f"THE COUNT MUST BE AN INTEGER, GOT {count!r}.")
        return int(count)

    def _size(self, ctx):
        count = self._count(ctx)
        if count < 0:
            raise SizeofError("A GREEDY ARRAY HAS NO FIXED SIZE.")
        return self._nbytes(count)

    def _build(self, data, stream, ctx):
        dtype = self.dtypefor(ctx)
        try:
            array = np.asarray(data, dtype=dtype).ravel()
        except (OverflowError, TypeError, ValueError) as error:
            raise ValidationError(
                f"CANNOT BUILD {data!r} AS {dtype} VALUES: {error}."
            ) from error
        count = self._count(ctx)
        if count >= 0:
            if array.size < count:
                raise ValidationError(
                    f"NOT ENOUGH DATA TO BUILD: NEED {count} ELEMENTS, GOT {array.size}."
                )
            array = array[:count]
        if self.packing is None:
            stream.write(array.tobytes())
            return array
        try:
            stream.write(packbits(array, self.packing, self.bitorder))
        except PaboError as error:
            raise ValidationError(error.msg) from None
        return array

    def _parse(self, stream, ctx):
        count = self._count(ctx)
        memory = buffer(stream) if self.packing is None else None
        if memory is not None:
            return self._parseview(stream, memory, count, self.dtypefor(ctx))
        if self.packing is None and count >= 0 and hasattr(stream, "readinto"):
            return self._parseinto(stream, count, self.dtypefor(ctx))
        raw = readexact(stream, self._nbytes(count)) if count >= 0 else stream.read()
        if self.packing is None:
            if len(raw) % self.dtype.width:
                raise StreamError(
                    f"{len(raw)} BYTES IS NOT A WHOLE NUMBER OF "
                    f"{self.dtype.width}-BYTE ELEMENTS."
                )
            return np.frombuffer(raw, dtype=self.dtypefor(ctx))
        values = unpackbits(raw, self.packing, self.bitorder)
        if count >= 0:
            values = values[:count]
        return values.astype(self.dtypefor(ctx))
