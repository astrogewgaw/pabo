import pytest

import pabo as pb


def test_bytes():
    """
    `Bytes` parses the first `count` bytes and builds data of that length.
    """
    assert pb.Bytes(3).parse(b"abcdef") == b"abc"
    assert pb.Bytes(3).build(b"abc") == b"abc"


def test_bytes_validation():
    """
    `Bytes` raises `PaboError` on wrong-length data or a short read, and with a
    negative count has no fixed size but parses everything that is left.
    """
    with pytest.raises(pb.PaboError):
        pb.Bytes(3).build(b"ab")
    with pytest.raises(pb.PaboError):
        pb.Bytes(3).parse(b"ab")
    with pytest.raises(pb.PaboError):
        pb.Bytes(-1).size
    assert pb.Bytes(-1).parse(b"all of it") == b"all of it"


def test_flag():
    """
    `Flag` parses a zero byte as False and any other byte as True, and builds True
    as a single one byte.
    """
    assert pb.Flag().parse(b"\x00") is False
    assert pb.Flag().parse(b"\x07") is True
    assert pb.Flag().build(True) == b"\x01"


def test_flag_eof_raises():
    """
    Parsing a `Flag` from empty data raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        pb.Flag().parse(b"")


def test_padding():
    """
    `Padding` builds and parses null bytes, has a size of its length, and raises
    `PaboError` when the padding bytes are not null.
    """
    assert pb.Padding(3).build() == b"\x00\x00\x00"
    assert pb.Padding(3).parse(b"\x00\x00\x00") == b"\x00\x00\x00"
    assert pb.Padding(3).size == 3
    with pytest.raises(pb.PaboError):
        pb.Padding(3).parse(b"\x00\x01\x00")


def test_greedy_bytes():
    """
    `GreedyBytes` parses all the remaining data and builds data unchanged.
    """
    assert pb.GreedyBytes().parse(b"abc") == b"abc"
    assert pb.GreedyBytes().build(b"abc") == b"abc"


def test_dynamic_count():
    """
    A `Bytes` count can come from an earlier field via `this`, and a count that
    resolves to a non-integer raises `PaboError`.
    """
    spec = pb.Spec({"n": pb.Int(1), "data": pb.Bytes(pb.this.n)})
    assert spec.parse(b"\x02ab") == {"n": 2, "data": b"ab"}
    with pytest.raises(pb.PaboError):
        pb.Bytes(lambda ctx: "x").parse(b"")
