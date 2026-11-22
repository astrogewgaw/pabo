from io import BytesIO

import numpy as np
import pytest

import pabo as pb
from pabo import this


def test_seek_and_tell():
    spec = pb.Spec({"a": pb.Int(1), "pos": pb.Tell(), "skip": pb.Seek(3), "b": pb.Int(1)})
    assert spec.parse(b"\x01\x00\x00\x02") == {"a": 1, "pos": 1, "skip": 3, "b": 2}
    stream = BytesIO(b"\x00" * 4)
    spec.build({"a": 1, "b": 2}, stream)
    assert stream.getvalue() == b"\x01\x00\x00\x02"
    with pytest.raises(pb.SizeofError):
        spec.size
    assert pb.Spec({"a": pb.Int(1), "pos": pb.Tell()}).size == 1


def test_seek_relative():
    spec = pb.Spec({"skip": pb.Seek(2, 1), "b": pb.Int(1)})
    assert spec.parse(b"\x00\x00\x07")["b"] == 7


def test_pointer():
    spec = pb.Spec(
        {
            "offset": pb.Int(1),
            "value": pb.Pointer(this.offset, pb.Int(2)),
            "next": pb.Int(1),
        }
    )
    raw = b"\x04\x09\x00\x00\x05\x00"
    assert spec.parse(raw) == {"offset": 4, "value": 5, "next": 9}
    assert spec.size == 2
    stream = BytesIO(bytearray(6))
    spec.build({"offset": 4, "value": 5, "next": 9}, stream)
    assert stream.getvalue() == b"\x04\x09\x00\x00\x05\x00"


def test_peek():
    spec = pb.Spec({"peeked": pb.Peek(pb.Int(2)), "a": pb.Int(1), "b": pb.Int(1)})
    assert spec.parse(b"\x01\x02") == {"peeked": 0x0201, "a": 1, "b": 2}
    assert spec.build({"a": 1, "b": 2}) == b"\x01\x02"
    assert spec.size == 2


def test_aligned():
    c = pb.Aligned(4, pb.CString())
    assert c.build("ab") == b"ab\x00\x00"
    assert c.build("abc") == b"abc\x00"
    assert c.build("abcd") == b"abcd\x00\x00\x00\x00"
    assert c.parse(b"ab\x00\x00rest") == "ab"
    assert pb.Aligned(4, pb.Int(2)).size == 4
    assert pb.Aligned(4, pb.Int(2), fill=b"\xff").build(1) == b"\x01\x00\xff\xff"
    with pytest.raises(pb.PaboError):
        pb.Aligned(0, pb.Int(1))


def test_aligned_spec():
    spec = pb.AlignedSpec(4, {"a": pb.Int(1), "b": pb.Int(2)}, endian="big")
    assert spec.build({"a": 1, "b": 2}) == b"\x01\x00\x00\x00\x00\x02\x00\x00"
    assert spec.size == 8
    assert spec.parse(spec.build({"a": 1, "b": 2})) == {"a": 1, "b": 2}


def test_lazy():
    spec = pb.Spec({"n": pb.Int(1), "data": pb.Lazy(pb.Bytes(this.n)), "end": pb.Int(1)})
    data = spec.parse(b"\x03abc\x09")
    assert isinstance(data.data, pb.LazyValue)
    assert "not parsed" in repr(data.data)
    assert data.end == 9
    assert data.data.offset == 1
    assert data.data.get() == b"abc" and data.data.value == b"abc"
    assert spec.build(data) == b"\x03abc\x09"
    assert spec.build({"n": 3, "data": b"xyz", "end": 1}) == b"\x03xyz\x01"
    with pytest.raises(pb.StreamError):
        spec.parse(b"\x05ab")


def test_lazy_from_file_after_parse(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"\x02\x00" + b"\x01\x00\x02\x00")
    spec = pb.Spec({"n": pb.Int(2), "xs": pb.Lazy(pb.Array(pb.Int(2), count=this.n))})
    data = spec.parse(path)
    np.testing.assert_array_equal(data.xs.get(), [1, 2])


def test_mmapped_arrays_are_zero_copy(tmp_path):
    path = tmp_path / "arr.bin"
    values = np.arange(1000, dtype="<f4")
    path.write_bytes(b"\x07" + values.tobytes())
    spec = pb.Spec({"tag": pb.Int(1), "xs": pb.Array(pb.Float(4))})
    data = spec.parse(path)
    np.testing.assert_array_equal(data.xs, values)
    assert not data.xs.flags.writeable
    assert not data.xs.flags.owndata
    counted = pb.Spec({"tag": pb.Int(1), "xs": pb.Array(pb.Float(4), count=2), "rest": pb.GreedyBytes()})
    data = counted.parse(path)
    np.testing.assert_array_equal(data.xs, [0, 1])
    assert len(data.rest) == 998 * 4
    with pytest.raises(pb.StreamError):
        pb.Spec({"xs": pb.Array(pb.Float(4), count=2000)}).parse(path)
    path.write_bytes(b"\x00" * 7)
    with pytest.raises(pb.StreamError):
        pb.Array(pb.Float(4)).parse(path)


def test_parse_empty_file(tmp_path):
    path = tmp_path / "empty.bin"
    path.write_bytes(b"")
    assert pb.GreedyBytes().parse(path) == b""
