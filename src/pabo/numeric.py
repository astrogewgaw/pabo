"""
Numerical constructs.
"""

import struct
from dataclasses import dataclass
from typing import Literal

import numpy as np

from pabo.base import Construct, PaboError, read_exactly
from pabo.packed import pack, unpack

Endian = Literal["little", "big", "native"]
BitOrder = Literal["big", "little"]

ENDIANS = {"little": "<", "big": ">", "native": "="}
INT_CODES = {1: "b", 2: "h", 4: "i", 8: "q"}
FLOAT_CODES = {4: "f", 8: "d"}


def _check_endian(endian: str) -> None:
    if endian not in ENDIANS:
        raise PaboError(
            f"Invalid endianness {endian!r}. Must be one of {list(ENDIANS)}."
        )


def _check_bitorder(bitorder: str) -> None:
    if bitorder not in ("big", "little"):
        raise PaboError(f"Invalid bit order {bitorder!r}. Must be 'big' or 'little'.")


class _Fixed(Construct):
    """
    Shared implementation for fixed-width numbers backed by `struct`.
    """

    @property
    def format(self) -> str:
        raise NotImplementedError

    def _size(self):
        return self.width

    def _build(self, data, stream) -> None:
        try:
            stream.write(struct.pack(self.format, data))
        except struct.error as error:
            raise PaboError(f"Cannot build {data!r} as {self!r}: {error}.") from error

    def _parse(self, stream):
        return struct.unpack(self.format, read_exactly(stream, self.width))[0]


@dataclass
class Int(_Fixed):
    """
    Represents a fixed-width integer.
    """

    width: int
    signed: bool = False
    endian: Endian = "little"

    def __post_init__(self):
        if self.width not in INT_CODES:
            raise PaboError(
                f"Unsupported integer width {self.width}. Must be one of {list(INT_CODES)}."
            )
        _check_endian(self.endian)

    @property
    def format(self) -> str:
        code = INT_CODES[self.width]
        return ENDIANS[self.endian] + (code if self.signed else code.upper())


@dataclass
class Float(_Fixed):
    """
    Represents a fixed-width floating point number.
    """

    width: int
    endian: Endian = "little"

    def __post_init__(self):
        if self.width not in FLOAT_CODES:
            raise PaboError(
                f"Unsupported float width {self.width}. Must be one of {list(FLOAT_CODES)}."
            )
        _check_endian(self.endian)

    @property
    def format(self) -> str:
        return ENDIANS[self.endian] + FLOAT_CODES[self.width]


@dataclass
class Array(Construct):
    """
    Represents an array of fixed-width numbers.

    A negative `count` reads until the end of the stream. If `packing` is set
    (1, 2 or 4), each element is stored in that many bits, `bitorder` decides
    whether the first element sits in the most ("big") or least ("little")
    significant bits of each byte, and the values are returned as `dtype`.
    """

    dtype: Int | Float
    count: int = -1
    packing: int | None = None
    bitorder: BitOrder = "big"

    def __post_init__(self):
        if self.packing is not None:
            if self.packing not in (1, 2, 4):
                raise PaboError(
                    f"Unsupported packing {self.packing}. Must be 1, 2 or 4."
                )
            if not isinstance(self.dtype, Int):
                raise PaboError("Only integer arrays can be packed.")
        _check_bitorder(self.bitorder)

    @property
    def numpy_dtype(self) -> np.dtype:
        return np.dtype(self.dtype.format)

    def _nbytes(self, count: int) -> int:
        if self.packing is None:
            return count * self.dtype.width
        return -(-count * self.packing // 8)

    def _size(self):
        if self.count < 0:
            raise PaboError("A greedy array has no fixed size.")
        return self._nbytes(self.count)

    def _build(self, data, stream):
        array = np.asarray(data, dtype=self.numpy_dtype).ravel()
        if self.count >= 0:
            if array.size < self.count:
                raise PaboError(
                    f"Not enough data to build: need {self.count} elements, got {array.size}."
                )
            array = array[: self.count]
        if self.packing is None:
            stream.write(array.tobytes())
            return
        if array.size and (array.min() < 0 or array.max() >= 1 << self.packing):
            raise PaboError(f"Values do not fit in {self.packing} bits.")
        per_byte = 8 // self.packing
        values = np.zeros(-(-array.size // per_byte) * per_byte, dtype=np.uint8)
        values[: array.size] = array
        stream.write(pack(values, nbits=self.packing, bitorder=self.bitorder).tobytes())

    def _parse(self, stream):
        if self.count >= 0:
            raw = read_exactly(stream, self._nbytes(self.count))
        else:
            raw = stream.read()
        if self.packing is None:
            if len(raw) % self.dtype.width:
                raise PaboError(
                    f"{len(raw)} bytes is not a whole number of "
                    f"{self.dtype.width}-byte elements."
                )
            return np.frombuffer(raw, dtype=self.numpy_dtype)
        values = unpack(
            np.frombuffer(raw, dtype=np.uint8),
            nbits=self.packing,
            bitorder=self.bitorder,
        )
        if self.count >= 0:
            values = values[: self.count]
        return values.astype(self.numpy_dtype)
