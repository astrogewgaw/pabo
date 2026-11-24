import io

import pytest

import pabo as pb

PNG = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\x0d"
    + b"IHDR"
    + b"\x00\x00\x02\x5a"
    + b"\x00\x00\x00\xac"
)


@pytest.fixture
def png():
    """
    A specification for the start of a PNG file: signature, IHDR chunk size and tag, and
    the big-endian image width and height.
    """
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
    """
    The README example: parsing a PNG header gives the expected field dict and the
    specification has a static `size`.
    """
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
    """
    Building the parsed PNG header gives back the original bytes.
    """
    assert png.build(png.parse(PNG)) == PNG


def test_parse_from_file(png, tmp_path):
    """
    `parse()` reads from a file given as a `Path` or a `str`.
    """
    path = tmp_path / "example.png"
    path.write_bytes(PNG)
    assert png.parse(path)["width"] == 602
    assert png.parse(str(path))["height"] == 172


def test_missing_field_raises(png):
    """
    Building with required fields missing from the input raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        png.build({"width": 1})


def test_nested():
    """
    A specification nested in another parses to a nested dict and round-trips.
    """
    inner = pb.Spec({"a": pb.Int(1), "b": pb.Int(1)})
    outer = pb.Spec({"x": inner, "y": pb.Int(2)})
    raw = b"\x01\x02\x03\x00"
    assert outer.parse(raw) == {"x": {"a": 1, "b": 2}, "y": 3}
    assert outer.build(outer.parse(raw)) == raw


def test_build_fills_in_constants(png):
    """
    `Const` fields can be left out when building and are filled in automatically.
    """
    data = {"ihdr_size": 13, "width": 602, "height": 172}
    assert png.build(data) == PNG


def test_build_with_padding():
    """
    `Padding` fields can be left out when building and are written as zero bytes.
    """
    c = pb.Spec({"a": pb.Int(1), "pad": pb.Padding(2), "b": pb.Int(1)})
    assert c.build({"a": 1, "b": 2}) == b"\x01\x00\x00\x02"


def test_nested_key_error_is_not_masked():
    """
    A field missing from a nested specification's input raises a `PaboError` that
    names the missing field (`'a'`).
    """
    inner = pb.Spec({"a": pb.Int(1)})
    outer = pb.Spec({"x": inner})
    with pytest.raises(pb.PaboError, match="'a'"):
        outer.build({"x": {}})


def test_dependent_fields():
    """
    Later fields can use earlier ones for their size or count, via `this.n` or a
    lambda, when both parsing and building.
    """
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
    """
    A nested specification can refer to a field of its parent via `this._.n`.
    """
    inner = pb.Spec({"data": pb.Bytes(pb.this._.n)})
    outer = pb.Spec({"n": pb.Int(1), "inner": inner})
    assert outer.parse(b"\x02ab") == {"n": 2, "inner": {"data": b"ab"}}
    assert outer.build({"n": 2, "inner": {"data": b"ab"}}) == b"\x02ab"


def test_build_requires_dict():
    """
    Building a specification from a non-mapping (a list) raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        pb.Spec({"a": pb.Int(1)}).build([1])


def test_embedded():
    """
    `Embedded` merges a specification's fields into the enclosing one, so later fields
    can refer to them; it also parses on its own.
    """
    common = pb.Spec({"a": pb.Int(1), "b": pb.Int(1)})
    spec = pb.Spec({"x": pb.Int(1), "_": pb.Embedded(common), "c": pb.Bytes(pb.this.a)})
    raw = b"\x09\x02\x03ab"
    data = spec.parse(raw)
    assert data == {"x": 9, "a": 2, "b": 3, "c": b"ab"}
    assert spec.build(data) == raw
    assert spec.sizeof(data) == 5
    assert pb.Embedded(common).parse(b"\x01\x02") == {"a": 1, "b": 2}


def test_nested_specs_roundtrip_deeply():
    """
    Specifications nested several levels deep, including inside a `Sequential`, give
    attribute access at every level and round-trip.
    """
    spec = pb.Spec(
        {
            "a": pb.Spec(
                {
                    "b": pb.Spec({"c": pb.Int(2)}),
                    "d": pb.Seq([pb.Int(1), pb.Spec({"e": pb.Int(1)})]),
                }
            )
        }
    )
    raw = b"\x01\x00\x02\x03"
    data = spec.parse(raw)
    assert data.a.b.c == 1 and data.a.d[1].e == 3
    assert spec.build(data) == raw


def test_docs_in_errors():
    """
    An error in a documented field carries the field's `docs` and quotes it in the
    message.
    """
    spec = pb.Spec({"w": pb.Int(4) / "Image width"})
    with pytest.raises(pb.StreamError) as info:
        spec.parse(b"\x00")
    assert info.value.docs == "Image width"
    assert "'Image width'" in str(info.value)


def test_trace(capsys):
    """
    `parse(..., trace=True)` prints each field with its byte range and value plus a hex
    dump to stderr, indenting nested specifications.
    """
    spec = pb.Spec({"a": pb.Int(1), "inner": pb.Spec({"b": pb.Int(2)})})
    spec.parse(b"\x01\x02\x00", trace=True)
    err = capsys.readouterr().err
    assert "a [0:1] = 1" in err
    assert "  b [1:3] = 2" in err
    assert "00000001  02 00" in err


def test_trace_to_stream():
    """
    `parse(..., trace=stream)` writes the trace to the given stream.
    """
    import io

    out = io.StringIO()
    pb.Spec({"a": pb.Int(1)}).parse(b"\x07", trace=out)
    assert "a [0:1] = 7" in out.getvalue()


def test_describe():
    """
    `describe()` lists each field's offset, size, name, type and docs, indenting nested
    specifications and showing `?` for sizes or offsets that are not known statically.
    """
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
    assert lines[1].split()[:3] == ["0", "2", "magic"] and lines[1].endswith(
        "Magic number"
    )
    assert lines[3].split()[:4] == ["3", "4", "hdr", "Specification(endian='big')"]
    assert lines[4].split()[:3] == ["3", "2", "w"]
    assert lines[6].split()[:3] == ["7", "?", "data"]
    assert lines[7].split()[:3] == ["?", "4", "crc"]
    assert pb.u16.describe().splitlines()[1].split()[:2] == ["0", "2"]


def test_compiled_plan_is_used_and_matches():
    """
    A fixed-size specification compiles to a single `struct` format, parses and builds
    the same as the slow path, and builds a `Flag` given as `1` or `True` as `1`.
    """
    spec = pb.Spec(
        {
            "magic": pb.Const(b"AB", pb.Bytes(2)),
            "a": pb.u16,
            "b": pb.i32,
            "c": pb.f64,
            "flag": pb.Flag(),
        },
        endian="big",
    )
    plan = spec._plan(pb.Context())
    assert plan is not None and plan.struct.format == ">2sHid?"
    raw = (
        b"AB" + b"\x00\x01" + b"\xff\xff\xff\xfe" + b"\x3f\xf8" + b"\x00" * 6 + b"\x02"
    )
    data = spec.parse(raw)
    assert data == {"magic": b"AB", "a": 1, "b": -2, "c": 1.5, "flag": True}
    assert spec.build(data) == raw[:-1] + b"\x01"
    assert spec.build({"a": 1, "b": -2, "c": 1.5, "flag": 1}) == raw[:-1] + b"\x01"


def test_compiled_plan_falls_back_for_detailed_errors():
    """
    When the compiled plan hits a bad constant, short read, out-of-range integer or
    wrong-length bytes, the error still names the failing field like the slow path.
    """
    spec = pb.Spec(
        {"magic": pb.Const(b"AB", pb.Bytes(2)), "a": pb.u16, "d": pb.Bytes(2)}
    )
    with pytest.raises(pb.ConstError) as info:
        spec.parse(b"XY\x00\x00ab")
    assert info.value.where == "magic"
    with pytest.raises(pb.StreamError) as info:
        spec.parse(b"AB\x00")
    assert info.value.where == "a"
    with pytest.raises(pb.ValidationError) as info:
        spec.build({"a": 70000, "d": b"ab"})
    assert info.value.where == "a"
    with pytest.raises(pb.ValidationError):
        spec.build({"a": 1, "d": b"abc"})
    with pytest.raises(pb.ConstError):
        spec.build({"magic": b"XY", "a": 1, "d": b"ab"})


def test_no_plan_for_mixed_or_dynamic_fields():
    """
    No compiled plan is made for mixed endianness, dynamic sizes or an empty
    specification.
    """
    assert pb.Spec({"a": pb.u16le, "b": pb.u16be})._plan(pb.Context()) is None
    assert pb.Spec({"n": pb.u8, "d": pb.Bytes(pb.this.n)})._plan(pb.Context()) is None
    assert pb.Spec({})._plan(pb.Context()) is None


def test_repeat_builds_in_bulk_like_one_by_one():
    """
    A `Repeat` of a fixed-size specification builds every element in one go, with
    the same bytes and returned values (constants filled in, flags as bools) as
    building them one at a time; a bad element still raises with its path.
    """
    spec = pb.Spec(
        {
            "magic": pb.Const(b"PB", pb.Bytes(2)),
            "flag": pb.Flag(),
            "n": pb.u16,
        }
    )
    data = [{"flag": 1, "n": i, "extra": "kept"} for i in range(4)]
    bulk = pb.Repeat(spec, 4)
    raw = bulk.build(data)
    assert raw == b"".join(spec.build(element) for element in data)
    stream = io.BytesIO()
    built = bulk._build(data, stream, pb.Context())
    assert built == [
        {"magic": b"PB", "flag": True, "n": i, "extra": "kept"} for i in range(4)
    ]
    assert all(type(element) is pb.Container for element in built)
    assert bulk.parse(raw) == [{"magic": b"PB", "flag": True, "n": i} for i in range(4)]
    data[2] = {"flag": 1, "n": -1}
    with pytest.raises(pb.PaboError) as info:
        bulk.build(data)
    assert info.value.where == "[2].n"
    three = pb.Repeat(spec, 3)
    assert three.build([*data[:2], {"flag": 0, "n": 7}]) == raw[:10] + b"PB\x00\x07\x00"


def test_compiled_plan_on_a_stream_that_cannot_rewind():
    """
    A fixed-size specification read from a stream without `tell`/`seek` is parsed
    field by field, with the same result.
    """

    class Forward:
        """
        A stream that can only read forwards.
        """

        def __init__(self, raw):
            self.raw = raw

        def read(self, size=-1):
            out, self.raw = self.raw[:size], self.raw[size:]
            return out

    spec = pb.Spec({"a": pb.u16, "b": pb.Const(b"!", pb.Bytes(1))})
    assert spec.parse(Forward(b"\x01\x00!")) == {"a": 1, "b": b"!"}


def test_fields_starting_with_an_underscore_are_left_out():
    """
    Fields whose names start with an underscore are parsed (and can be referred
    to) but left out of the result, on every path: compiled, field by field, in
    bulk, embedded and when building.
    """

    fixed = pb.Spec({"a": pb.u8, "_reserved": pb.Padding(2), "b": pb.u8})
    assert fixed.parse(b"\x01\x00\x00\x02") == {"a": 1, "b": 2}
    assert fixed.build({"a": 1, "b": 2}) == b"\x01\x00\x00\x02"
    assert fixed._build({"a": 1, "b": 2}, io.BytesIO(), pb.Context()) == {
        "a": 1,
        "b": 2,
    }
    assert pb.Repeat(fixed, 2).parse(b"\x01\x00\x00\x02" * 2) == [{"a": 1, "b": 2}] * 2
    assert pb.Repeat(fixed, 2).build([{"a": 1, "b": 2}] * 2) == b"\x01\x00\x00\x02" * 2
    dynamic = pb.Spec({"_n": pb.u8, "data": pb.Bytes(pb.this._n)})
    assert dynamic.parse(b"\x02ab") == {"data": b"ab"}
    assert dynamic.build({"_n": 2, "data": b"ab"}) == b"\x02ab"
    outer = pb.Spec({"x": pb.u8, "_": pb.Embedded(fixed)})
    assert outer.parse(b"\x09\x01\x00\x00\x02") == {"x": 9, "a": 1, "b": 2}
