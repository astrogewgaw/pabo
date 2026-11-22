"""
Bit manipulation.
"""

from dataclasses import dataclass, field

import numpy as np

from pabo.base import Construct, read_exactly
from pabo.context import Container
from pabo.errors import PaboError, ValidationError
from pabo.numeric import BitOrder, _check_bitorder
from pabo.packing import pack_bits, unpack_bits


@dataclass
class Bits(Construct):
    """
    Represents `count` bits, as bytes with one 0 or 1 per bit.

    The bits occupy ceil(count / 8) bytes, so `size` is in bytes, like every
    other construct. Unused trailing bits are zero when building and ignored
    when parsing. `bitorder` decides whether the first bit is the most ("big")
    or least ("little") significant bit of each byte.
    """

    count: int
    bitorder: BitOrder = "big"

    def __post_init__(self):
        if self.count < 0:
            raise PaboError("The number of bits cannot be negative.")
        _check_bitorder(self.bitorder)

    def _size(self, ctx):
        return -(-self.count // 8)

    def _build(self, bits, stream, ctx):
        if isinstance(bits, (bytes, bytearray, memoryview)):
            values = np.frombuffer(bits, dtype=np.uint8)
        else:
            values = np.asarray(bits, dtype=np.uint8).ravel()
        if values.size != self.count:
            raise ValidationError(f"Expected {self.count} bits, got {values.size}.")
        if (values > 1).any():
            raise ValidationError("Bits must be 0 or 1.")
        padded = np.zeros(self.size * 8, dtype=np.uint8)
        padded[: self.count] = values
        stream.write(pack_bits(padded, 1, self.bitorder))
        return bits

    def _parse(self, stream, ctx):
        raw = read_exactly(stream, self.size)
        bits = unpack_bits(raw, 1, self.bitorder)
        return bits[: self.count].tobytes()


@dataclass
class BitInt:
    """
    An integer of `nbits` bits inside a `BitStruct`.
    """

    nbits: int
    signed: bool = False

    def __post_init__(self):
        if self.nbits < 1:
            raise PaboError("A bit field needs at least one bit.")


@dataclass
class BitFlag:
    """
    A single bit inside a `BitStruct`, as a boolean.
    """

    nbits: int = field(default=1, init=False)
    signed: bool = field(default=False, init=False)


@dataclass
class BitPadding:
    """
    `nbits` zero bits inside a `BitStruct`, left out of the parsed result.
    """

    nbits: int
    signed: bool = field(default=False, init=False)

    def __post_init__(self):
        if self.nbits < 1:
            raise PaboError("Bit padding needs at least one bit.")


@dataclass
class BitStruct(Construct[Container]):
    """
    Named integer fields narrower than a byte, packed together.

    The fields (`BitInt`, `BitFlag`, `BitPadding`) must add up to a whole
    number of bytes. With `bitorder="big"` (network order, as in IP and most
    file formats), the bytes are read as a big-endian integer and the first
    field takes its most significant bits. With `bitorder="little"` (C bit
    fields on little-endian machines), the bytes are read as a little-endian
    integer and the first field takes its least significant bits.
    """

    fields: dict[str, BitInt | BitFlag | BitPadding]
    bitorder: BitOrder = "big"

    def __post_init__(self):
        _check_bitorder(self.bitorder)
        total = sum(spec.nbits for spec in self.fields.values())
        if total % 8:
            raise PaboError(
                f"The bit fields add up to {total} bits, which is not a whole number of bytes."
            )

    def _layout(self):
        """
        Yield (name, spec, shift) for every field.
        """

        total = sum(spec.nbits for spec in self.fields.values())
        used = 0
        for name, spec in self.fields.items():
            shift = total - used - spec.nbits if self.bitorder == "big" else used
            used += spec.nbits
            yield name, spec, shift

    def _size(self, ctx):
        return sum(spec.nbits for spec in self.fields.values()) // 8

    def _build(self, data, stream, ctx):
        value = 0
        for name, spec, shift in self._layout():
            if isinstance(spec, BitPadding):
                continue
            if name not in data:
                raise PaboError(f"Missing bit field {name!r}.")
            field_value = int(data[name])
            lo, hi = (
                (-(1 << (spec.nbits - 1)), 1 << (spec.nbits - 1))
                if spec.signed
                else (0, 1 << spec.nbits)
            )
            if not lo <= field_value < hi:
                raise ValidationError(
                    f"The value {field_value} of bit field {name!r} does not fit in {spec.nbits} bits."
                )
            value |= (field_value & ((1 << spec.nbits) - 1)) << shift
        stream.write(value.to_bytes(self._size(ctx), self.bitorder))
        return data

    def _parse(self, stream, ctx):
        raw = read_exactly(stream, self._size(ctx))
        value = int.from_bytes(raw, self.bitorder)
        out = Container()
        for name, spec, shift in self._layout():
            if isinstance(spec, BitPadding):
                continue
            field_value = (value >> shift) & ((1 << spec.nbits) - 1)
            if spec.signed and field_value >> (spec.nbits - 1):
                field_value -= 1 << spec.nbits
            out[name] = bool(field_value) if isinstance(spec, BitFlag) else field_value
        return out
