import numpy as np
import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


@pytest.mark.parametrize("width", [1, 2, 4, 8])
@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("endian", ["little", "big"])
def test_int_roundtrip(width, signed, endian):
    c = pb.Int(width, signed=signed, endian=endian)
    value = -(2 ** (8 * width - 1)) if signed else 2 ** (8 * width) - 1
    raw = c.build(value)
    assert raw == value.to_bytes(width, endian, signed=signed)
    assert c.parse(raw) == value
    assert c.size == width


@pytest.mark.parametrize("width", [4, 8])
@pytest.mark.parametrize("endian", ["little", "big"])
def test_float_roundtrip(width, endian):
    c = pb.Float(width, endian=endian)
    assert c.parse(c.build(1.5)) == 1.5
    assert len(c.build(1.5)) == width


def test_int_format_is_public():
    assert pb.Int(4, signed=True, endian="big").format == ">i"
    assert pb.Float(8).format == "<d"
    assert pb.Int(2).format_for("big") == ">H"
    with pytest.raises(pb.PaboError):
        pb.Int(3).format


@pytest.mark.parametrize("width", [3, 5, 16])
@pytest.mark.parametrize("signed", [False, True])
@pytest.mark.parametrize("endian", ["little", "big", "native"])
def test_odd_width_ints(width, signed, endian):
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
    c = pb.Float(2, endian="big")
    assert c.build(1.5) == b"\x3e\x00"
    assert c.parse(b"\x3e\x00") == 1.5
    np.testing.assert_array_equal(pb.Array(pb.Float(2)).parse(b"\x00\x3e"), [1.5])


@pytest.mark.parametrize(
    "value, raw",
    [(0, b"\x00"), (1, b"\x01"), (127, b"\x7f"), (128, b"\x80\x01"), (300, b"\xac\x02")],
)
def test_varint(value, raw):
    assert pb.VarInt().build(value) == raw
    assert pb.VarInt().parse(raw + b"rest") == value


def test_varint_errors():
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
    raw = pb.ZigZag().build(value)
    assert raw == pb.VarInt().build(encoded)
    assert pb.ZigZag().parse(raw) == value


def test_zigzag_errors():
    with pytest.raises(pb.ValidationError):
        pb.ZigZag().build(1.5)
    with pytest.raises(pb.SizeofError):
        pb.ZigZag().size


def test_endianness_inherited_from_spec():
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
    raw = b"\x00\x01" + b"\x01\x00" + b"\x3f\x80\x00\x00" + b"\x00\x00\x01" + b"\x00\x01" + b"\x00\x01"
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
    c = pb.Array(dtype, count=3)
    raw = c.build([1, -2, 3])
    assert len(raw) == 3 * dtype.width
    np.testing.assert_array_equal(c.parse(raw), [1, -2, 3])


def test_array_greedy_count():
    c = pb.Array(pb.Int(1))
    np.testing.assert_array_equal(c.parse(b"\x01\x02\x03"), [1, 2, 3])


def test_array_size_in_bytes():
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
    # beartype may reject a bad Literal before pabo's own validation runs.
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        make()


def test_native_endian():
    c = pb.Int(4, endian="native")
    assert c.parse(c.build(7)) == 7


def test_int_out_of_range_and_short_read():
    with pytest.raises(pb.PaboError):
        pb.Int(1).build(256)
    with pytest.raises(pb.PaboError):
        pb.Int(4).parse(b"\x00\x00")


def test_array_short_read_and_trailing_bytes():
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
    c = pb.Array(pb.Int(2), count=count, packing=packing, bitorder=bitorder)
    values = [i % (1 << packing) for i in range(count)]
    raw = c.build(values)
    assert len(raw) == c.size == -(-count * packing // 8)
    parsed = c.parse(raw + b"trailing")
    assert parsed.dtype == np.dtype("<u2")
    np.testing.assert_array_equal(parsed, values)


def test_packed_array_validation():
    with pytest.raises(pb.PaboError):
        pb.Array(pb.Int(1), count=2, packing=2).build([1, 4])
    with pytest.raises(pb.PaboError):
        pb.Array(pb.Float(4), packing=2)
    with pytest.raises(pb.PaboError):
        pb.Array(pb.Int(1), packing=3)


def test_packed_array_greedy():
    c = pb.Array(pb.Int(1), packing=4)
    np.testing.assert_array_equal(c.parse(b"\x12\x34"), [1, 2, 3, 4])
