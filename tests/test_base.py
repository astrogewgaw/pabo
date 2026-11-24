from io import BytesIO

import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


def test_parse_bytes_like():
    """
    `parse()` accepts `bytes`, `bytearray` and `memoryview` inputs alike.
    """
    c = pb.Int(2)
    assert c.parse(b"\x01\x00") == 1
    assert c.parse(bytearray(b"\x01\x00")) == 1
    assert c.parse(memoryview(b"\x01\x00")) == 1


def test_build_into_open_file(tmp_path):
    """
    `build()` writes into an open file object and returns None instead of the bytes.
    """
    path = tmp_path / "out.bin"
    with open(path, "wb") as f:
        assert pb.Int(2).build(1, f) is None
    assert path.read_bytes() == b"\x01\x00"


def test_build_into_stream():
    """
    `build()` writes into an in-memory `BytesIO` stream passed as the target.
    """
    stream = BytesIO()
    pb.Int(2).build(1, stream)
    assert stream.getvalue() == b"\x01\x00"


def test_build_to_path_truncates_unless_appending(tmp_path):
    """
    `build()` to a path truncates the file by default and appends with `append=True`;
    a `Const` can be built to a path with no value given.
    """
    path = tmp_path / "out.bin"
    pb.Int(1).build(1, path)
    pb.Int(1).build(2, path)
    assert path.read_bytes() == b"\x02"
    pb.Int(1).build(3, path, append=True)
    assert path.read_bytes() == b"\x02\x03"
    pb.Const(b"A", pb.Bytes(1)).build(src=path)
    assert path.read_bytes() == b"A"


def test_unsupported_targets():
    """
    `build()` and `parse()` reject a target that is not bytes, a path or a stream (an
    `int`) with a `PaboError` or a beartype violation.
    """
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Int(1).build(1, 42)
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Int(1).parse(42)


def test_docs_operator():
    """
    `construct / "text"` sets the construct's `docs` field.
    """
    c = pb.Int(4) / "a field"
    assert c.docs == "a field"


def test_docs_is_a_field():
    """
    `docs` is a keyword dataclass field defaulting to an empty string, and the `/`
    operator gives a construct equal to one built with `docs=`.
    """
    assert pb.Int(4, docs="width").docs == "width"
    assert pb.Int(4).docs == ""
    assert (pb.Int(4) / "x") == pb.Int(4, docs="x")


def test_docs_operator_returns_a_copy():
    """
    The `/` operator returns a documented copy and leaves the original unchanged.
    """
    c = pb.Int(4)
    d = c / "doc"
    assert c.docs == "" and d.docs == "doc"


def test_docs_operator_rejects_non_str():
    """
    Using `/` with a non-string operand raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        pb.Int(4) / 3


def test_sizeof_static_and_dynamic():
    """
    `sizeof()` works for fixed-size constructs; a size depending on `this.n` makes
    `size` raise `SizeofError` but `sizeof({"n": 3})` resolves it.
    """
    assert pb.Int(4).sizeof() == 4
    c = pb.Bytes(pb.this.n)
    with pytest.raises(pb.SizeofError):
        c.size
    assert c.sizeof({"n": 3}) == 3


def test_sizeof_of_spec_after_parsing():
    """
    A specification with a dynamic field has no static `size` (`SizeofError`), but
    `sizeof()` given the parsed values returns its full size.
    """
    spec = pb.Spec({"n": pb.Int(1), "data": pb.Bytes(pb.this.n)})
    data = spec.parse(b"\x03abc")
    with pytest.raises(pb.SizeofError):
        spec.size
    assert spec.sizeof(data) == 4


def test_nested_sizeof():
    """
    `sizeof()` resolves dynamic sizes in a nested specification from the nested part
    of the given context.
    """
    inner = pb.Spec({"n": pb.Int(1), "data": pb.Bytes(pb.this.n)})
    outer = pb.Spec({"a": pb.Int(2), "inner": inner})
    assert outer.sizeof({"inner": {"n": 5}}) == 8


def test_custom_construct():
    """
    A user-defined `Construct` subclass implementing only `_size`, `_parse` and `_build`
    works with the public `parse()` and `build()`.
    """
    from dataclasses import dataclass

    @dataclass
    class Nibbles(pb.Construct):
        """
        A custom construct: one byte, split into its two 4-bit halves.
        """

        def _size(self, ctx):
            return 1

        def _parse(self, stream, ctx):
            byte = pb.base.readexact(stream, 1)[0]
            return byte >> 4, byte & 15

        def _build(self, data, stream, ctx):
            stream.write(bytes([data[0] << 4 | data[1]]))
            return data

    c = Nibbles()
    assert c.parse(b"\x12") == (1, 2)
    assert c.build((1, 2)) == b"\x12"


def test_beartype_can_be_disabled():
    """
    Setting `PABOROAR=0` turns off runtime type checking at import, while
    `PABOROAR=1` makes a bad argument raise `BeartypeCallHintParamViolation`.
    """
    import os
    import subprocess
    import sys

    code = "import pabo; pabo.Int('x')"
    env = {**os.environ, "PABOROAR": "0"}
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert "Beartype" not in result.stderr
    env["PABOROAR"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert "BeartypeCallHintParamViolation" in result.stderr


def test_hexdump():
    """
    `hexdump()` formats 16 bytes per line with the offset, hex bytes padded to full
    width and printable ASCII, using `.` for unprintable bytes.
    """
    from pabo.base import hexdump

    assert hexdump(b"AB\x00", 16) == "00000010  41 42 00" + " " * 39 + "  AB."
    assert len(hexdump(bytes(40)).splitlines()) == 3


def test_repr_shows_docs_only_when_set():
    """
    `repr` of a construct looks like a dataclass repr, adding `docs=...` at the end
    only when docs are set (also for nested and user-defined constructs).
    """
    from dataclasses import dataclass

    assert repr(pb.Int(2)) == "Int(width=2, signed=False, endian=None)"
    assert repr(pb.Int(2) / "Width") == (
        "Int(width=2, signed=False, endian=None, docs='Width')"
    )
    assert "docs='A'" in repr(pb.Spec({"a": pb.u8 / "A"}))

    @dataclass
    class Mine(pb.Construct):
        """
        A minimal user-defined construct.
        """

        n: int = 1

        def _size(self, ctx):
            return 0

        def _parse(self, stream, ctx):
            return None

        def _build(self, data, stream, ctx):
            return data

    assert repr(Mine()) == "Mine(n=1)"
    assert repr(Mine(docs="mine")) == "Mine(n=1, docs='mine')"


def test_parameters_for_parse_and_build():
    """
    Keyword arguments to `parse` and `build` are parameters that fields read as
    `this._params.name` or `ctx._params.name`, at any depth; a missing one raises
    a `ContextError`.
    """

    inner = pb.Spec({"values": pb.Array(pb.u8, count=pb.this._params.nchans)})
    spec = pb.Spec(
        {
            "frame": inner,
            "scaled": pb.Computed(
                lambda ctx: ctx.frame["values"].sum() * ctx._params.scale
            ),
        }
    )
    data = spec.parse(b"\x01\x02\x03\x04", nchans=3, scale=2)
    assert list(data.frame["values"]) == [1, 2, 3] and data.scaled == 12
    assert (
        spec.build({"frame": {"values": [1, 2, 3, 9]}}, nchans=3, scale=1)
        == b"\x01\x02\x03"
    )
    with pytest.raises(pb.ContextError, match="_params"):
        inner.parse(b"\x01")


def test_parameters_for_class_based_structs():
    """
    `Struct.parse` and `Struct.build` pass parameters on to their fields.
    """

    class Frame(pb.Struct):
        """
        A frame of `n` bytes, given as a parameter.
        """

        data: bytes = pb.Bytes(pb.this._params.n)

    frame = Frame.parse(b"abcd", n=2)
    assert frame.data == b"ab"
    assert frame.build(n=2) == b"ab"


def test_strict_parse_rejects_leftover_bytes(tmp_path):
    """
    `parse(..., strict=True)` raises a `StreamError` for bytes left over after
    the data, from bytes, files and streams; by default they are ignored.
    """

    c = pb.Spec({"a": pb.u16})
    assert c.parse(b"\x01\x00extra") == {"a": 1}
    assert c.parse(b"\x01\x00", strict=True) == {"a": 1}
    with pytest.raises(pb.StreamError, match="5 BYTES WERE LEFT OVER"):
        c.parse(b"\x01\x00extra", strict=True)
    path = tmp_path / "data.bin"
    path.write_bytes(b"\x01\x00!")
    with pytest.raises(pb.StreamError, match="1 BYTES"):
        c.parse(path, strict=True)
    with pytest.raises(pb.StreamError):
        c.parse(BytesIO(b"\x01\x00!"), strict=True)


def test_parse_with_offsets():
    """
    `parse(..., offsets=True)` gives each parsed specification an `_offsets`
    attribute mapping its fields to their (start, end) offsets, also for nested
    and repeated ones, and the values are the same as without it.
    """

    inner = pb.Spec({"x": pb.u16, "y": pb.u8})
    spec = pb.Spec(
        {
            "n": pb.u8,
            "text": pb.Bytes(pb.this.n),
            "points": pb.Repeat(inner, 2),
            "_pad": pb.Padding(1),
        }
    )
    raw = b"\x02hi\x01\x00\x02\x03\x00\x04\x00"
    data = spec.parse(raw, offsets=True)
    assert data == spec.parse(raw)
    assert data._offsets == {"n": (0, 1), "text": (1, 3), "points": (3, 9)}
    assert data.points[1]._offsets == {"x": (6, 8), "y": (8, 9)}
    assert not hasattr(spec.parse(raw), "_offsets")


def test_dump_names_the_fields_on_each_line():
    """
    `dump` shows a hex dump with the fields that start on each line (with their
    full paths) at its end, and colours each field when asked.
    """

    spec = pb.Spec(
        {
            "magic": pb.Bytes(8),
            "size": pb.u32,
            "points": pb.Repeat(pb.Spec({"x": pb.u16, "y": pb.u16}), 2),
        }
    )
    raw = b"\x89PNG\r\n\x1a\n" + bytes(4) + bytes(range(8))
    lines = spec.dump(raw).splitlines()
    assert lines[0].startswith(
        "00000000  89 50 4e 47 0d 0a 1a 0a 00 00 00 00 00 01 02 03"
    )
    assert lines[0].endswith(".PNG............  magic, size, points[0].x, points[0].y")
    assert lines[1].startswith("00000010  04 05 06 07")
    assert lines[1].endswith("points[1].x, points[1].y")
    colored = spec.dump(raw, color=True)
    assert "\x1b[31m89\x1b[0m" in colored and "\x1b[31mmagic\x1b[0m" in colored
