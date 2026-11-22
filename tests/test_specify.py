import pytest

import pabo as pb

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0d" + b"IHDR" + b"\x00\x00\x02\x5a" + b"\x00\x00\x00\xac"


@pytest.fixture
def png():
    return pb.Spec(
        {
            "magic": pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8)),
            "ihdr_size": pb.Int(4, endian="big"),
            "ihdr_id": pb.Const(b"IHDR", pb.Bytes(4)),
            "width": pb.Int(4, endian="big"),
            "height": pb.Int(4, endian="big"),
        }
    )


def test_readme_example(png):
    data = png.parse(PNG)
    assert data == {
        "magic": b"\x89PNG\r\n\x1a\n",
        "ihdr_size": 13,
        "ihdr_id": b"IHDR",
        "width": 602,
        "height": 172,
    }
    assert png.size == len(PNG)


def test_roundtrip(png):
    assert png.build(png.parse(PNG)) == PNG


def test_parse_from_file(png, tmp_path):
    path = tmp_path / "example.png"
    path.write_bytes(PNG)
    assert png.parse(path)["width"] == 602
    assert png.parse(str(path))["height"] == 172


def test_missing_field_raises(png):
    with pytest.raises(pb.PaboError):
        png.build({"width": 1})


def test_nested():
    inner = pb.Spec({"a": pb.Int(1), "b": pb.Int(1)})
    outer = pb.Spec({"x": inner, "y": pb.Int(2)})
    raw = b"\x01\x02\x03\x00"
    assert outer.parse(raw) == {"x": {"a": 1, "b": 2}, "y": 3}
    assert outer.build(outer.parse(raw)) == raw


def test_build_fills_in_constants(png):
    data = {"ihdr_size": 13, "width": 602, "height": 172}
    assert png.build(data) == PNG


def test_build_with_padding():
    c = pb.Spec({"a": pb.Int(1), "pad": pb.Padding(2), "b": pb.Int(1)})
    assert c.build({"a": 1, "b": 2}) == b"\x01\x00\x00\x02"


def test_nested_key_error_is_not_masked():
    inner = pb.Spec({"a": pb.Int(1)})
    outer = pb.Spec({"x": inner})
    with pytest.raises(pb.PaboError, match="'a'"):
        outer.build({"x": {}})
