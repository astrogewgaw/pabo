import numpy as np
import pytest
from beartype.roar import BeartypeCallHintParamViolation
from hypothesis import given
from hypothesis import strategies as st

import pabo as pb


@pytest.mark.parametrize("width", [1, 2, 4, 8])
@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("endian", ["little", "big"])
def test_int_roundtrip(width, signed, endian):
    """
    `Int`s of every struct width (1, 2, 4, 8), signedness and endianness build their
    extreme value to `int.to_bytes`' layout, parse it back and have `size == width`.
    """

    c = pb.Int(width, signed=signed, endian=endian)
    value = -(2 ** (8 * width - 1)) if signed else 2 ** (8 * width) - 1
    raw = c.build(value)
    assert raw == value.to_bytes(width, endian, signed=signed)
    assert c.parse(raw) == value
    assert c.size == width


@pytest.mark.parametrize("width", [4, 8])
@pytest.mark.parametrize("endian", ["little", "big"])
def test_float_roundtrip(width, endian):
    """
    32- and 64-bit `Float`s in both endiannesses round-trip 1.5 and build exactly
    `width` bytes.
    """

    c = pb.Float(width, endian=endian)
    assert c.parse(c.build(1.5)) == 1.5
    assert len(c.build(1.5)) == width


def test_int_format_is_public():
    """
    `Int.format`, `Float.format` and `Int.formatfor()` give the matching `struct` format
    strings, and `format` raises `PaboError` for a width with no struct code (3).
    """

    assert pb.Int(4, signed=True, endian="big").format == ">i"
    assert pb.Float(8).format == "<d"
    assert pb.Int(2).formatfor("big") == ">H"
    with pytest.raises(pb.PaboError):
        pb.Int(3).format


@pytest.mark.parametrize("width", [3, 5, 16])
@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("endian", ["little", "big", "native"])
def test_odd_width_ints(width, signed, endian):
    """
    `Int`s of non-struct widths (3, 5, 16) round-trip like `int.to_bytes` in every
    endianness; out-of-range values raise `ValidationError`, short reads `StreamError`.
    """

    import sys

    c = pb.Int(width, signed=signed, endian=endian)
    value = -(2 ** (8 * width - 1)) if signed else 2 ** (8 * width) - 1
    raw = c.build(value)
    order = sys.byteorder if endian == "native" else endian
    assert raw == value.to_bytes(width, order, signed=signed)
    assert c.parse(raw) == value
    assert c.size == width
    with pytest.raises(pb.ValidationError):
        c.build(2 ** (8 * width))
    with pytest.raises(pb.StreamError):
        c.parse(raw[:-1])


def test_half_float():
    """
    A 2-byte `Float` (half precision) builds and parses 1.5, both on its own and as
    the element type of an `Array`.
    """

    c = pb.Float(2, endian="big")
    assert c.build(1.5) == b"\x3e\x00"
    assert c.parse(b"\x3e\x00") == 1.5
    np.testing.assert_array_equal(pb.Array(pb.Float(2)).parse(b"\x00\x3e"), [1.5])


@pytest.mark.parametrize(
    "value, raw",
    [
        (0, b"\x00"),
        (1, b"\x01"),
        (127, b"\x7f"),
        (128, b"\x80\x01"),
        (300, b"\xac\x02"),
    ],
)
def test_varint(value, raw):
    """
    `VarInt` builds each value to its known LEB128 encoding and parses it back,
    ignoring bytes that follow.
    """

    assert pb.VarInt().build(value) == raw
    assert pb.VarInt().parse(raw + b"rest") == value


def test_varint_errors():
    """
    `VarInt` raises `ValidationError` for negative values, `StreamError` when the
    stream ends mid-number, and `SizeofError` for `size`.
    """

    with pytest.raises(pb.ValidationError):
        pb.VarInt().build(-1)
    with pytest.raises(pb.StreamError):
        pb.VarInt().parse(b"\x80")
    with pytest.raises(pb.SizeofError):
        pb.VarInt().size


@pytest.mark.parametrize(
    "value, encoded", [(0, 0), (-1, 1), (1, 2), (-2, 3), (2, 4), (-(2**40), 2**41 - 1)]
)
def test_zigzag(value, encoded):
    """
    `ZigZag` maps signed values to the expected unsigned codes (0, -1, 1, -2, ...),
    stores them as a `VarInt`, and parses them back.
    """

    raw = pb.ZigZag().build(value)
    assert raw == pb.VarInt().build(encoded)
    assert pb.ZigZag().parse(raw) == value


def test_zigzag_errors():
    """
    `ZigZag` raises `ValidationError` when building a non-integer and `SizeofError`
    for `size`.
    """

    with pytest.raises(pb.ValidationError):
        pb.ZigZag().build(1.5)
    with pytest.raises(pb.SizeofError):
        pb.ZigZag().size


def test_endianness_inherited_from_spec():
    """
    Numeric fields without an explicit endianness (including odd-width `Int`s, `Array`
    and nested specs) use the enclosing `Spec`'s, while explicit ones and inner specs
    with their own endianness keep theirs, and a standalone `Int` stays little-endian.
    """

    spec = pb.Spec(
        {
            "a": pb.Int(2),
            "b": pb.Int(2, endian="little"),
            "c": pb.Float(4),
            "d": pb.Int(3),
            "e": pb.Array(pb.Int(2), count=1),
            "inner": pb.Spec({"f": pb.Int(2)}),
        },
        endian="big",
    )
    raw = (
        b"\x00\x01"
        + b"\x01\x00"
        + b"\x3f\x80\x00\x00"
        + b"\x00\x00\x01"
        + b"\x00\x01"
        + b"\x00\x01"
    )
    data = spec.parse(raw)
    assert (data.a, data.b, data.c, data.d, data.inner.f) == (1, 1, 1.0, 1, 1)
    assert data.e.dtype == np.dtype(">u2")
    assert spec.build(data) == raw
    inner = pb.Spec({"f": pb.Int(2)}, endian="little")
    outer = pb.Spec({"x": pb.Int(2), "inner": inner}, endian="big")
    assert outer.parse(b"\x00\x01\x01\x00") == {"x": 1, "inner": {"f": 1}}
    assert pb.Int(2).parse(b"\x01\x00") == 1


@pytest.mark.parametrize("dtype", [pb.Int(2, signed=True), pb.Float(4, endian="big")])
def test_array_roundtrip(dtype):
    """
    Fixed-count `Array`s of a signed `Int` and a big-endian `Float` build
    `count * width` bytes and parse back to the same values.
    """

    c = pb.Array(dtype, count=3)
    raw = c.build([1, -2, 3])
    assert len(raw) == 3 * dtype.width
    np.testing.assert_array_equal(c.parse(raw), [1, -2, 3])


def test_array_greedy_count():
    """
    An `Array` with no count parses every element left in the stream.
    """

    c = pb.Array(pb.Int(1))
    np.testing.assert_array_equal(c.parse(b"\x01\x02\x03"), [1, 2, 3])


def test_array_size_in_bytes():
    """
    A fixed-count `Array`'s `size` is the element width times the count, in bytes.
    """

    assert pb.Array(pb.Int(4), count=3).size == 12


@pytest.mark.parametrize(
    "make",
    [
        lambda: pb.Int(0),
        lambda: pb.Float(3),
        lambda: pb.Int(4, endian="middle"),
        lambda: pb.Array(pb.Int(3)),
    ],
)
def test_invalid_numeric_construction(make):
    """
    Invalid constructor arguments (zero width, a 3-byte `Float`, unknown endianness,
    an `Array` of a non-struct-width `Int`) are rejected at construction.
    """

    # beartype may reject a bad Literal before pabo's own validation runs.
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        make()


def test_native_endian():
    """
    An `Int` with native endianness round-trips a value.
    """

    c = pb.Int(4, endian="native")
    assert c.parse(c.build(7)) == 7


def test_int_out_of_range_and_short_read():
    """
    `Int` raises `PaboError` when building a value too large for its width and when
    parsing from too few bytes.
    """

    with pytest.raises(pb.PaboError):
        pb.Int(1).build(256)
    with pytest.raises(pb.PaboError):
        pb.Int(4).parse(b"\x00\x00")


def test_array_short_read_and_trailing_bytes():
    """
    `Array` raises `PaboError` on a short read with a fixed count, when a greedy read
    leaves a partial element, and for the `size` of a greedy array.
    """

    with pytest.raises(pb.PaboError):
        pb.Array(pb.Int(4), count=2).parse(b"\x00" * 7)
    with pytest.raises(pb.PaboError):
        pb.Array(pb.Int(4)).parse(b"\x00" * 7)
    with pytest.raises(pb.PaboError):
        pb.Array(pb.Int(4)).size


@pytest.mark.parametrize("packing", [1, 2, 4])
@pytest.mark.parametrize("bitorder", ["big", "little"])
@pytest.mark.parametrize("count", [8, 5])
def test_packed_array_roundtrip(packing, bitorder, count):
    """
    `Array`s packed at 1, 2 or 4 bits in both bit orders, with whole (8) and partial (5)
    final bytes, take the expected number of bytes, ignore trailing input and parse
    back with the element dtype.
    """

    c = pb.Array(pb.Int(2), count=count, packing=packing, bitorder=bitorder)
    values = [i % (1 << packing) for i in range(count)]
    raw = c.build(values)
    assert len(raw) == c.size == -(-count * packing // 8)
    parsed = c.parse(raw + b"trailing")
    assert parsed.dtype == np.dtype("<u2")
    np.testing.assert_array_equal(parsed, values)


def test_packed_array_validation():
    """
    Packed `Array`s raise `PaboError` for values that do not fit the packing, a `Float`
    element type, and a packing above the element width or of zero.
    """

    with pytest.raises(pb.PaboError):
        pb.Array(pb.Int(1), count=2, packing=2).build([1, 4])
    with pytest.raises(pb.PaboError):
        pb.Array(pb.Float(4), packing=2)


@pytest.mark.parametrize("packing", [0, 3, 5, 8, 12, 16])
def test_unsupported_packing_is_rejected(packing):
    """
    Only 1, 2 and 4-bit packing is supported; any other width is rejected when the
    `Array` is created.
    """

    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Array(pb.Int(2), count=7, packing=packing)


def test_packed_array_greedy():
    """
    A packed `Array` with no count unpacks every value in the remaining bytes.
    """

    c = pb.Array(pb.Int(1), packing=4)
    np.testing.assert_array_equal(c.parse(b"\x12\x34"), [1, 2, 3, 4])


def test_array_reads_into_new_buffer():
    """
    Parsing an `Array` from a regular stream reads into a fresh writeable array and
    leaves the stream just past it; a short stream raises `StreamError`.
    """

    from io import BytesIO

    stream = BytesIO(np.arange(4, dtype=">u2").tobytes() + b"rest")
    parsed = pb.Array(pb.Int(2, endian="big"), count=4).parse(stream)
    np.testing.assert_array_equal(parsed, [0, 1, 2, 3])
    assert parsed.flags.writeable
    assert stream.read() == b"rest"
    with pytest.raises(pb.StreamError):
        pb.Array(pb.Int(2), count=4).parse(BytesIO(b"\x00" * 7))


def test_array_reads_from_short_reads():
    """
    `Array` keeps calling `readinto` until it has the whole array when the stream
    returns one byte at a time, and never falls back to `read()`.
    """

    class Trickle:
        """
        A stream whose `readinto` returns one byte at a time, and has no `read`.
        """

        def __init__(self, raw):
            self.raw = raw

        def readinto(self, view):
            n = min(1, len(self.raw), len(view))
            view[:n] = self.raw[:n]
            self.raw = self.raw[n:]
            return n

        def read(self, size=-1):
            raise AssertionError("read() should not be used")

    parsed = pb.Array(pb.Int(2), count=2).parse(Trickle(b"\x01\x00\x02\x00"))
    np.testing.assert_array_equal(parsed, [1, 2])


@given(
    width=st.integers(1, 16),
    signed=st.booleans(),
    endian=st.sampled_from(["little", "big"]),
    data=st.data(),
)
def test_int_roundtrip_property(width, signed, endian, data):
    """
    For any width from 1 to 16 bytes, signedness, endianness and in-range value, `Int`
    builds `int.to_bytes`' output and parses it back.
    """

    bits = 8 * width
    lo, hi = (-(2 ** (bits - 1)), 2 ** (bits - 1) - 1) if signed else (0, 2**bits - 1)
    value = data.draw(st.integers(lo, hi))
    c = pb.Int(width, signed=signed, endian=endian)
    raw = c.build(value)
    assert raw == value.to_bytes(width, endian, signed=signed)
    assert c.parse(raw) == value


@given(st.floats(width=32, allow_nan=False), st.sampled_from(["little", "big"]))
def test_float_roundtrip_property(value, endian):
    """
    Every non-NaN 32-bit float round-trips through a 4-byte `Float` in either
    endianness.
    """

    c = pb.Float(4, endian=endian)
    assert c.parse(c.build(value)) == value


@given(st.integers(min_value=0, max_value=2**100))
def test_varint_roundtrip_property(value):
    """
    Every non-negative integer up to 2**100 round-trips through `VarInt`.
    """

    assert pb.VarInt().parse(pb.VarInt().build(value)) == value


@given(st.integers(min_value=-(2**100), max_value=2**100))
def test_zigzag_roundtrip_property(value):
    """
    Every integer between -2**100 and 2**100 round-trips through `ZigZag`.
    """

    assert pb.ZigZag().parse(pb.ZigZag().build(value)) == value


@given(
    packing=st.sampled_from([1, 2, 4]),
    bitorder=st.sampled_from(["big", "little"]),
    data=st.data(),
)
def test_packed_array_roundtrip_property(packing, bitorder, data):
    """
    For any packing from 1 to 16 bits, either bit order and any list of values that
    fit, a packed `Array` parses back what it built.
    """

    values = data.draw(st.lists(st.integers(0, 2**packing - 1), max_size=50))
    c = pb.Array(pb.Int(2), count=len(values), packing=packing, bitorder=bitorder)
    np.testing.assert_array_equal(c.parse(c.build(values)), values)
