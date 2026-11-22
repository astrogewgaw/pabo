import pytest

import pabo as pb
from hypothesis import given
from hypothesis import strategies as st


def test_bits_size_in_bytes():
    assert pb.Bits(8).size == 1
    assert pb.Bits(12).size == 2


@pytest.mark.parametrize("bitorder", ["big", "little"])
@pytest.mark.parametrize("count", [8, 12, 3])
def test_bits_roundtrip(bitorder, count):
    c = pb.Bits(count, bitorder=bitorder)
    bits = bytes(i % 2 for i in range(count))
    raw = c.build(bits)
    assert len(raw) == c.size
    assert c.parse(raw) == bits
    assert c.build(list(bits)) == raw


def test_bits_order():
    assert pb.Bits(8).parse(b"\x80") == b"\x01" + b"\x00" * 7
    assert pb.Bits(8, bitorder="little").parse(b"\x80") == b"\x00" * 7 + b"\x01"
    assert pb.Bits(3).parse(b"\xa0") == b"\x01\x00\x01"


def test_bits_in_spec_size():
    assert pb.Spec({"flags": pb.Bits(16), "n": pb.Int(2)}).size == 4


def test_bits_validation():
    with pytest.raises(pb.PaboError):
        pb.Bits(8).build(b"\x01" * 7)
    with pytest.raises(pb.PaboError):
        pb.Bits(2).build(b"\x01\x02")


def test_bitstruct_ipv4_header_byte():
    c = pb.BitStruct({"version": pb.BitInt(4), "ihl": pb.BitInt(4)})
    assert c.parse(b"\x45") == {"version": 4, "ihl": 5}
    assert c.build({"version": 4, "ihl": 5}) == b"\x45"
    assert c.size == 1


def test_bitstruct_flags_padding_and_signed():
    c = pb.BitStruct(
        {
            "a": pb.BitFlag(),
            "pad": pb.BitPadding(3),
            "b": pb.BitInt(4, signed=True),
            "c": pb.BitInt(8),
        }
    )
    raw = c.build({"a": True, "b": -2, "c": 0xAB})
    assert raw == bytes([0b1000_1110, 0xAB])
    assert c.parse(raw) == {"a": True, "b": -2, "c": 0xAB}


def test_bitstruct_little_bitorder():
    c = pb.BitStruct({"lo": pb.BitInt(4), "hi": pb.BitInt(12)}, bitorder="little")
    raw = c.build({"lo": 0x1, "hi": 0xABC})
    assert int.from_bytes(raw, "little") == 0xABC1
    assert c.parse(raw) == {"lo": 1, "hi": 0xABC}


def test_bitstruct_errors():
    with pytest.raises(pb.PaboError):
        pb.BitStruct({"a": pb.BitInt(3)})
    with pytest.raises(pb.PaboError):
        pb.BitInt(0)
    c = pb.BitStruct({"a": pb.BitInt(4), "b": pb.BitInt(4, signed=True)})
    with pytest.raises(pb.ValidationError):
        c.build({"a": 16, "b": 0})
    with pytest.raises(pb.ValidationError):
        c.build({"a": 0, "b": 8})
    with pytest.raises(pb.PaboError):
        c.build({"a": 0})
    with pytest.raises(pb.StreamError):
        c.parse(b"")


def test_bitstruct_in_spec():
    spec = pb.Spec({"flags": pb.BitStruct({"x": pb.BitInt(8)}), "n": pb.Int(1)})
    assert spec.parse(b"\x01\x02") == {"flags": {"x": 1}, "n": 2}
    assert spec.size == 2



@given(st.lists(st.integers(0, 1), max_size=100), st.sampled_from(["big", "little"]))
def test_bits_roundtrip_property(bits, bitorder):
    c = pb.Bits(len(bits), bitorder)
    assert list(c.parse(c.build(bits))) == bits


@given(st.lists(st.integers(1, 12), min_size=1, max_size=8), st.data())
def test_bitstruct_roundtrip_property(widths, data):
    total = sum(widths)
    widths = widths + ([8 - total % 8] if total % 8 else [])
    fields = {f"f{ix}": pb.BitInt(n) for ix, n in enumerate(widths)}
    for bitorder in ("big", "little"):
        c = pb.BitStruct(fields, bitorder)
        values = {name: data.draw(st.integers(0, 2**f.nbits - 1)) for name, f in fields.items()}
        assert c.parse(c.build(values)) == values
