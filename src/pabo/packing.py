"""
Packing and unpacking of integers narrower than a byte (or not byte-aligned).
"""

from typing import Literal

import numpy as np

from pabo import packed
from pabo.errors import PaboError

BitOrder = Literal["big", "little"]


def _check(nbits: int, bitorder: str) -> None:
    if not 1 <= nbits <= 64:
        raise PaboError(f"Unsupported number of bits {nbits}. Must be from 1 to 64.")
    if bitorder not in ("big", "little"):
        raise PaboError(f"Invalid bit order {bitorder!r}. Must be 'big' or 'little'.")


def unpackbits(raw, nbits: int, bitorder: BitOrder = "big") -> np.ndarray:
    """
    Unpack every `nbits`-bit integer from the bytes in `raw`.

    With `bitorder="big"`, the first value sits in the most significant bits of
    the first byte, and each value's bits run from most to least significant.
    With `bitorder="little"`, both run the other way, so the first value sits in
    the least significant bits. 1, 2 and 4 bits use the C++ extension and give
    `uint8`; other widths use numpy and give `uint64`. Trailing bits that do not
    make up a whole value are dropped.
    """

    _check(nbits, bitorder)
    raw = np.frombuffer(raw, dtype=np.uint8) if not isinstance(raw, np.ndarray) else raw
    raw = np.ascontiguousarray(raw, dtype=np.uint8)
    if nbits in (1, 2, 4):
        return packed.unpack(raw, nbits=nbits, bitorder=bitorder)
    if nbits == 8:
        return raw.astype(np.uint64)
    bits = np.unpackbits(raw, bitorder=bitorder)
    count = bits.size // nbits
    bits = bits[: count * nbits].reshape(count, nbits).astype(np.uint64)
    shifts = np.arange(nbits, dtype=np.uint64)
    if bitorder == "big":
        shifts = shifts[::-1]
    values = np.zeros(count, dtype=np.uint64)
    for ix in range(nbits):
        values |= bits[:, ix] << shifts[ix]
    return values


def packbits(values, nbits: int, bitorder: BitOrder = "big") -> bytes:
    """
    Pack non-negative integers into `nbits` bits each (the inverse of `unpackbits`).

    The last byte is padded with zero bits. Values must fit in `nbits` bits.
    """

    _check(nbits, bitorder)
    values = np.asarray(values).ravel()
    if values.size and (
        values.min() < 0 or (nbits < 64 and values.max() >= 1 << nbits)
    ):
        raise PaboError(f"Values do not fit in {nbits} bits.")
    values = values.astype(np.uint64)
    if nbits in (1, 2, 4):
        per_byte = 8 // nbits
        padded = np.zeros(-(-values.size // per_byte) * per_byte, dtype=np.uint8)
        padded[: values.size] = values
        return packed.pack(padded, nbits=nbits, bitorder=bitorder).tobytes()
    shifts = np.arange(nbits, dtype=np.uint64)
    if bitorder == "big":
        shifts = shifts[::-1]
    bits = ((values[:, None] >> shifts[None, :]) & np.uint64(1)).astype(np.uint8)
    return np.packbits(bits.ravel(), bitorder=bitorder).tobytes()
