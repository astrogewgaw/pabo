import pytest

import pabo as pb


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
