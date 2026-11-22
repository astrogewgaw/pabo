import pytest

import pabo as pb


def test_bytes():
    assert pb.Bytes(3).parse(b"abcdef") == b"abc"
    assert pb.Bytes(3).build(b"abc") == b"abc"


def test_bytes_validation():
    with pytest.raises(pb.PaboError):
        pb.Bytes(3).build(b"ab")
    with pytest.raises(pb.PaboError):
        pb.Bytes(3).parse(b"ab")
    with pytest.raises(pb.PaboError):
        pb.Bytes(-1).size
    assert pb.Bytes(-1).parse(b"all of it") == b"all of it"


def test_flag():
    assert pb.Flag().parse(b"\x00") is False
    assert pb.Flag().parse(b"\x07") is True
    assert pb.Flag().build(True) == b"\x01"


def test_flag_eof_raises():
    with pytest.raises(pb.PaboError):
        pb.Flag().parse(b"")


def test_padding():
    assert pb.Padding(3).build() == b"\x00\x00\x00"
    assert pb.Padding(3).parse(b"\x00\x00\x00") == b"\x00\x00\x00"
    assert pb.Padding(3).size == 3
    with pytest.raises(pb.PaboError):
        pb.Padding(3).parse(b"\x00\x01\x00")
