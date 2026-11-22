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
