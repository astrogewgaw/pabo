import dataclasses
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


class PNGHeader(pb.Struct, endian="big"):
    """
    The start of a PNG file, as a class-based specification.
    """

    magic: bytes = pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8))
    ihdr_size: int = pb.Int(4)
    ihdr_id: bytes = pb.Const(b"IHDR", pb.Bytes(4))
    width: int = pb.Int(4)
    height: int = pb.Int(4)


def test_parse_into_instance():
    """
    Parsing a class-based `Struct` (a PNG header) returns a dataclass instance of that
    class that builds back to the same bytes and has the right `sizeof()`.
    """
    header = PNGHeader.parse(PNG)
    assert isinstance(header, PNGHeader)
    assert (header.width, header.height) == (602, 172)
    assert dataclasses.is_dataclass(header)
    assert header.build() == PNG
    assert PNGHeader.sizeof() == len(PNG)


def test_construct_instance_with_defaults():
    """
    A `Struct` can be instantiated with keyword arguments only, `Const` fields are
    filled in by default, and positional or missing arguments raise `TypeError`.
    """
    header = PNGHeader(ihdr_size=13, width=602, height=172)
    assert header.magic == b"\x89PNG\r\n\x1a\n"
    assert header.build() == PNG
    with pytest.raises(TypeError):
        PNGHeader(13, 602, 172)
    with pytest.raises(TypeError):
        PNGHeader(width=1)


def test_annotations_and_field_order():
    """
    Dataclass fields of a `Struct` keep their declaration order and type annotations.
    """
    names = [f.name for f in dataclasses.fields(PNGHeader)]
    assert names == ["magic", "ihdr_size", "ihdr_id", "width", "height"]
    assert dataclasses.fields(PNGHeader)[3].type is int


def test_inheritance_and_nesting():
    """
    A `Struct` subclass inherits the parent's fields and endianness, and a `Struct` can
    be nested in another via `construct()`, built from an instance or a plain dict.
    """

    class Base(pb.Struct, endian="big"):
        """
        A struct whose fields subclasses inherit.
        """

        a = pb.Int(2)

    class Child(Base):
        """
        Adds a field and a computed field after those of `Base`.
        """

        b = pb.Int(2)
        total = pb.Computed(lambda ctx: ctx.a + ctx.b)

    child = Child.parse(b"\x00\x01\x00\x02")
    assert (child.a, child.b, child.total) == (1, 2, 3)
    assert Child(a=1, b=2).build() == b"\x00\x01\x00\x02"

    class Outer(pb.Struct):
        """
        Nests `Child` with `Child.construct()`.
        """

        n = pb.u8
        inner = Child.construct()

    outer = Outer.parse(b"\x05\x00\x01\x00\x02")
    assert isinstance(outer.inner, Child) and outer.inner.total == 3
    assert outer.build() == b"\x05\x00\x01\x00\x02"
    assert Outer(n=5, inner={"a": 1, "b": 2}).build() == b"\x05\x00\x01\x00\x02"
    assert Outer.sizeof() == 5


def test_to_and_from_dict():
    """
    `todict()` and `fromdict()` convert a parsed `Struct` to a dict and back.
    """
    header = PNGHeader.parse(PNG)
    assert header.todict()["width"] == 602
    assert PNGHeader.fromdict(header.todict()) == header


def test_repeat_of_structs_is_parsed_in_bulk():
    """
    A `Repeat` of a fixed-size `Struct` parses all its instances in one go, with
    the same results as one at a time, and still reports a short stream.
    """
    import struct

    class Point(pb.Struct):
        """
        A fixed-size struct.
        """

        x: int = pb.i16
        y: float = pb.f32

    raw = b"".join(struct.pack("<hf", i, i / 2) for i in range(5))
    points = pb.Repeat(Point.construct(), 5).parse(raw)
    assert points == [Point(x=i, y=i / 2) for i in range(5)]
    assert all(type(p) is Point for p in points)
    one_by_one = pb.Repeat(Point.construct(), 5).parse(raw, trace=io.StringIO())
    assert one_by_one == points
    with pytest.raises(pb.StreamError):
        pb.Repeat(Point.construct(), 6).parse(raw)
