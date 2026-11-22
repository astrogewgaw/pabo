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


def test_dependent_fields():
    spec = pb.Spec(
        {
            "n": pb.Int(1),
            "data": pb.Bytes(pb.this.n),
            "words": pb.Repeat(pb.Int(2), lambda ctx: ctx.n - 1),
        }
    )
    raw = b"\x03abc\x01\x00\x02\x00"
    data = spec.parse(raw)
    assert data == {"n": 3, "data": b"abc", "words": [1, 2]}
    assert spec.build(data) == raw


def test_reference_to_parent_field():
    inner = pb.Spec({"data": pb.Bytes(pb.this._.n)})
    outer = pb.Spec({"n": pb.Int(1), "inner": inner})
    assert outer.parse(b"\x02ab") == {"n": 2, "inner": {"data": b"ab"}}
    assert outer.build({"n": 2, "inner": {"data": b"ab"}}) == b"\x02ab"


def test_build_requires_dict():
    with pytest.raises(pb.PaboError):
        pb.Spec({"a": pb.Int(1)}).build([1])


def test_embedded():
    common = pb.Spec({"a": pb.Int(1), "b": pb.Int(1)})
    spec = pb.Spec({"x": pb.Int(1), "_": pb.Embedded(common), "c": pb.Bytes(pb.this.a)})
    raw = b"\x09\x02\x03ab"
    data = spec.parse(raw)
    assert data == {"x": 9, "a": 2, "b": 3, "c": b"ab"}
    assert spec.build(data) == raw
    assert spec.sizeof(data) == 5
    assert pb.Embedded(common).parse(b"\x01\x02") == {"a": 1, "b": 2}


def test_nested_specs_roundtrip_deeply():
    spec = pb.Spec(
        {"a": pb.Spec({"b": pb.Spec({"c": pb.Int(2)}), "d": pb.Seq([pb.Int(1), pb.Spec({"e": pb.Int(1)})])})}
    )
    raw = b"\x01\x00\x02\x03"
    data = spec.parse(raw)
    assert data.a.b.c == 1 and data.a.d[1].e == 3
    assert spec.build(data) == raw


def test_docs_in_errors():
    spec = pb.Spec({"w": pb.Int(4) / "Image width"})
    with pytest.raises(pb.StreamError) as info:
        spec.parse(b"\x00")
    assert info.value.docs == "Image width"
    assert "'Image width'" in str(info.value)


def test_trace(capsys):
    spec = pb.Spec({"a": pb.Int(1), "inner": pb.Spec({"b": pb.Int(2)})})
    spec.parse(b"\x01\x02\x00", trace=True)
    err = capsys.readouterr().err
    assert "a [0:1] = 1" in err
    assert "  b [1:3] = 2" in err
    assert "00000001  02 00" in err


def test_trace_to_stream():
    import io

    out = io.StringIO()
    pb.Spec({"a": pb.Int(1)}).parse(b"\x07", trace=out)
    assert "a [0:1] = 7" in out.getvalue()


def test_describe():
    spec = pb.Spec(
        {
            "magic": pb.Const(b"PB", pb.Bytes(2)) / "Magic number",
            "n": pb.u8,
            "hdr": pb.Spec({"w": pb.u16, "h": pb.u16}, endian="big"),
            "data": pb.Bytes(pb.this.n),
            "crc": pb.u32,
        }
    )
    lines = spec.describe().splitlines()
    assert lines[0].split() == ["offset", "size", "field", "type", "docs"]
    assert lines[1].split()[:3] == ["0", "2", "magic"] and lines[1].endswith("Magic number")
    assert lines[3].split()[:4] == ["3", "4", "hdr", "Specification(endian='big')"]
    assert lines[4].split()[:3] == ["3", "2", "w"]
    assert lines[6].split()[:3] == ["7", "?", "data"]
    assert lines[7].split()[:3] == ["?", "4", "crc"]
    assert pb.u16.describe().splitlines()[1].split()[:2] == ["0", "2"]
