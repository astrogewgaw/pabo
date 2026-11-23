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
    Setting `PABO_BEARTYPE=0` turns off runtime type checking at import, while
    `PABO_BEARTYPE=1` makes a bad argument raise `BeartypeCallHintParamViolation`.
    """
    import os
    import subprocess
    import sys

    code = "import pabo; pabo.Int('x')"
    env = {**os.environ, "PABO_BEARTYPE": "0"}
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert "Beartype" not in result.stderr
    env["PABO_BEARTYPE"] = "1"
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
