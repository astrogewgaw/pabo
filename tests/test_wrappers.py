import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


def test_sequential():
    c = pb.Seq([pb.Int(1), pb.Flag()])
    assert c.parse(b"\x05\x01") == [5, True]
    assert c.build([5, True]) == b"\x05\x01"
    assert len(c) == 2


def test_repeat():
    c = pb.Repeat(pb.Int(2), 2)
    assert c.parse(b"\x01\x00\x02\x00") == [1, 2]
    assert c.build([1, 2]) == b"\x01\x00\x02\x00"
    assert c.size == 4
    with pytest.raises(pb.PaboError):
        c.build([1])


def test_adapted():
    c = pb.Adapted(pb.Int(1), decode=lambda x: x * 2, encode=lambda x: x // 2)
    assert c.parse(b"\x03") == 6
    assert c.build(6) == b"\x03"


def test_prefixed():
    c = pb.Prefixed(pb.Int(2), pb.Bytes(-1))
    assert c.build(b"abc") == b"\x03\x00abc"
    assert c.parse(b"\x03\x00abcXYZ") == b"abc"


def test_greedy_over_bytes():
    c = pb.Greedy(pb.Const(b"A", pb.Bytes(1)))
    assert c.parse(b"AAB") == [b"A", b"A"]


def test_greedy_over_int():
    assert pb.Greedy(pb.Int(2)).parse(b"\x01\x00\x02\x00") == [1, 2]


def test_greedy_rewinds_after_partial_element():
    from io import BytesIO

    stream = BytesIO(b"\x01\x00\x02\x00\x03")
    assert pb.Greedy(pb.Int(2)).parse(stream) == [1, 2]
    assert stream.read() == b"\x03"


def test_greedy_has_no_size():
    with pytest.raises(pb.PaboError):
        pb.Greedy(pb.Int(2)).size


def test_sequential_length_mismatch():
    with pytest.raises(pb.PaboError):
        pb.Seq([pb.Int(1), pb.Int(1)]).build([1])


def test_prefixed_counts_bytes_not_elements():
    c = pb.Prefixed(pb.Int(1), pb.Array(pb.Int(4)))
    raw = c.build([1, 2])
    assert raw[0] == 8
    assert list(c.parse(raw)) == [1, 2]
    with pytest.raises(pb.PaboError):
        c.size


def test_padded_keeps_trailing_nulls():
    c = pb.Padded(2, pb.Bytes(3))
    assert c.build(b"a\x00\x00") == b"a\x00\x00\x00\x00"
    assert c.parse(b"a\x00\x00\x00\x00") == b"a\x00\x00"
    assert c.size == 5


def test_const_parse():
    c = pb.Const(b"AB", pb.Bytes(2))
    assert c.parse(b"AB") == b"AB"
    with pytest.raises(pb.PaboError):
        c.parse(b"XY")


def test_const_build():
    c = pb.Const(b"AB", pb.Bytes(2))
    assert c.build() == b"AB"
    assert c.build(b"AB") == b"AB"
    with pytest.raises(pb.PaboError):
        c.build(b"XY")


def test_padded_fill_and_side():
    c = pb.Padded(2, pb.Int(1), fill=b"\xff", side="left")
    assert c.build(1) == b"\xff\xff\x01"
    assert c.parse(b"\xff\xff\x01") == 1
    assert pb.Padded(1, pb.Int(1), fill=b" ").build(1) == b"\x01 "
    with pytest.raises(pb.PaboError):
        pb.Padded(1, pb.Int(1), fill=b"ab")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Padded(1, pb.Int(1), side="up")
