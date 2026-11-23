import hashlib
import zlib

import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


@pytest.mark.parametrize("codec", ["zlib", "gzip", "bz2", "lzma"])
def test_compressed_roundtrip(codec):
    c = pb.Compressed(pb.GreedyString(), codec)
    text = "hello " * 100
    raw = c.build(text)
    assert len(raw) < len(text)
    assert c.parse(raw) == text


def test_compressed_inside_prefixed():
    spec = pb.Spec(
        {
            "body": pb.Prefixed(pb.Int(2), pb.Compressed(pb.Array(pb.Int(2)))),
            "after": pb.Int(1),
        }
    )
    raw = spec.build({"body": list(range(50)), "after": 7})
    data = spec.parse(raw)
    assert list(data.body) == list(range(50)) and data.after == 7


def test_compressed_with_size():
    payload = zlib.compress(b"abc")
    spec = pb.Spec(
        {
            "n": pb.Int(1),
            "body": pb.Compressed(pb.GreedyBytes(), length=pb.this.n),
            "x": pb.Int(1),
        }
    )
    raw = bytes([len(payload)]) + payload + b"\x05"
    assert spec.parse(raw) == {"n": len(payload), "body": b"abc", "x": 5}
    assert spec.sizeof({"n": len(payload)}) == len(payload) + 2
    with pytest.raises(pb.SizeofError):
        pb.Compressed(pb.Int(1)).size
    with pytest.raises(pb.ValidationError):
        spec.build({"n": 1, "body": b"abc", "x": 5})


def test_transform_errors():
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Compressed(pb.GreedyBytes(), "rot13")
    with pytest.raises(pb.ValidationError):
        pb.Compressed(pb.GreedyBytes()).parse(b"not zlib")


def test_transformed_custom():
    xor = lambda raw: bytes(b ^ 0xFF for b in raw)
    c = pb.Transformed(pb.Int(2), xor, xor, length=2)
    assert c.build(1) == b"\xfe\xff"
    assert c.parse(b"\xfe\xff") == 1
    assert c.size == 2


def test_checksummed_crc32():
    c = pb.Checksummed(pb.Bytes(3), pb.Int(4), "crc32")
    raw = c.build(b"abc")
    assert raw == b"abc" + zlib.crc32(b"abc").to_bytes(4, "little")
    assert c.parse(raw) == b"abc"
    assert c.size == 7
    with pytest.raises(pb.ValidationError):
        c.parse(b"abd" + raw[3:])


def test_checksummed_hashlib_and_function():
    c = pb.Checksummed(pb.Spec({"a": pb.Int(1), "b": pb.Int(1)}), pb.Bytes(16), "md5")
    raw = c.build({"a": 1, "b": 2})
    assert raw[2:] == hashlib.md5(b"\x01\x02").digest()
    assert c.parse(raw) == {"a": 1, "b": 2}
    s = pb.Checksummed(pb.Bytes(2), pb.Int(1), lambda raw: sum(raw) % 256)
    assert s.build(b"\x01\x02") == b"\x01\x02\x03"
    with pytest.raises(pb.PaboError):
        pb.Checksummed(pb.Bytes(1), pb.Int(1), "nope")
