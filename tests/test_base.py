from io import BytesIO

import pytest

import pabo as pb


def test_parse_bytes_like():
    c = pb.Int(2)
    assert c.parse(b"\x01\x00") == 1
    assert c.parse(bytearray(b"\x01\x00")) == 1
    assert c.parse(memoryview(b"\x01\x00")) == 1


def test_build_into_open_file(tmp_path):
    path = tmp_path / "out.bin"
    with open(path, "wb") as f:
        assert pb.Int(2).build(1, f) is None
    assert path.read_bytes() == b"\x01\x00"


def test_build_into_stream():
    stream = BytesIO()
    pb.Int(2).build(1, stream)
    assert stream.getvalue() == b"\x01\x00"


def test_build_to_path_truncates_unless_appending(tmp_path):
    path = tmp_path / "out.bin"
    pb.Int(1).build(1, path)
    pb.Int(1).build(2, path)
    assert path.read_bytes() == b"\x02"
    pb.Int(1).build(3, path, append=True)
    assert path.read_bytes() == b"\x02\x03"
    pb.Const(b"A", pb.Bytes(1)).build(src=path)
    assert path.read_bytes() == b"A"


def test_unsupported_targets():
    with pytest.raises(pb.PaboError):
        pb.Int(1).build(1, 42)
    with pytest.raises(pb.PaboError):
        pb.Int(1).parse(42)


def test_docs_operator():
    c = pb.Int(4) / "a field"
    assert c.docs == "a field"


def test_docs_is_a_field():
    assert pb.Int(4, docs="width").docs == "width"
    assert pb.Int(4).docs == ""
    assert (pb.Int(4) / "x") == pb.Int(4, docs="x")


def test_error_is_not_a_dataclass():
    import dataclasses

    assert not dataclasses.is_dataclass(pb.PaboError)


def test_docs_operator_returns_a_copy():
    c = pb.Int(4)
    d = c / "doc"
    assert c.docs == "" and d.docs == "doc"


def test_docs_operator_rejects_non_str():
    with pytest.raises(pb.PaboError):
        pb.Int(4) / 3


def test_sizeof_static_and_dynamic():
    assert pb.Int(4).sizeof() == 4
    c = pb.Bytes(pb.this.n)
    with pytest.raises(pb.SizeofError):
        c.size
    assert c.sizeof({"n": 3}) == 3


def test_sizeof_of_spec_after_parsing():
    spec = pb.Spec({"n": pb.Int(1), "data": pb.Bytes(pb.this.n)})
    data = spec.parse(b"\x03abc")
    with pytest.raises(pb.SizeofError):
        spec.size
    assert spec.sizeof(data) == 4


def test_nested_sizeof():
    inner = pb.Spec({"n": pb.Int(1), "data": pb.Bytes(pb.this.n)})
    outer = pb.Spec({"a": pb.Int(2), "inner": inner})
    assert outer.sizeof({"inner": {"n": 5}}) == 8


def test_custom_construct():
    from dataclasses import dataclass

    @dataclass
    class Nibbles(pb.Construct):
        def _size(self, ctx):
            return 1

        def _parse(self, stream, ctx):
            byte = pb.base.read_exactly(stream, 1)[0]
            return byte >> 4, byte & 15

        def _build(self, data, stream, ctx):
            stream.write(bytes([data[0] << 4 | data[1]]))
            return data

    c = Nibbles()
    assert c.parse(b"\x12") == (1, 2)
    assert c.build((1, 2)) == b"\x12"
