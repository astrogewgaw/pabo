"""
Packing and unpacking of integers narrower than a byte: 1, 2 or 4 bits each.

Both directions use the C++ extension (`pabo.packed`). Other widths are not
supported, and raise a `PaboError`.
"""

from collections.abc import Sequence
from typing import Any

import numpy as np

from pabo import packed
from pabo.errors import PaboError
from pabo.hints import BitOrder, BytesLike, NBits

#: The bit widths that can be packed.
WIDTHS = (1, 2, 4)


def _check(nbits: int, bitorder: str) -> None:
    if nbits not in WIDTHS:
        raise PaboError(f"UNSUPPORTED NUMBER OF BITS {nbits}. MUST BE 1, 2 OR 4.")
    if bitorder not in ("big", "little"):
        raise PaboError(f"INVALID BIT ORDER {bitorder!r}. MUST BE 'big' OR 'little'.")


def unpackbits(
    raw: BytesLike | np.ndarray, nbits: NBits, bitorder: BitOrder = "big"
) -> np.ndarray:
    """
    Unpack every `nbits`-bit integer (1, 2 or 4 bits) from the bytes in `raw`.

    With `bitorder="big"`, the first value sits in the most significant bits of
    the first byte, and each value's bits run from most to least significant.
    With `bitorder="little"`, both run the other way, so the first value sits in
    the least significant bits. Returns a `uint8` array with `8 // nbits` values
    per byte.
    """

    _check(nbits, bitorder)
    raw = np.frombuffer(raw, dtype=np.uint8) if not isinstance(raw, np.ndarray) else raw
    raw = np.ascontiguousarray(raw, dtype=np.uint8)
    return packed.unpack(raw, nbits=nbits, bitorder=bitorder)


def packbits(
    values: np.ndarray | Sequence[Any], nbits: NBits, bitorder: BitOrder = "big"
) -> bytes:
    """
    Pack non-negative integers into `nbits` bits each (the inverse of `unpackbits`).

    The last byte is padded with zero bits. Values must fit in `nbits` bits.
    """

    _check(nbits, bitorder)
    values = np.asarray(values).ravel()
    if values.size and (values.min() < 0 or values.max() >= 1 << nbits):
        raise PaboError(f"VALUES DO NOT FIT IN {nbits} BITS.")
    per_byte = 8 // nbits
    padded = np.zeros(-(-values.size // per_byte) * per_byte, dtype=np.uint8)
    padded[: values.size] = values
    return packed.pack(padded, nbits=nbits, bitorder=bitorder).tobytes()
