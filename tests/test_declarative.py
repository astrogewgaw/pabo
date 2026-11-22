import dataclasses

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
    magic: bytes = pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8))
    ihdr_size: int = pb.Int(4)
    ihdr_id: bytes = pb.Const(b"IHDR", pb.Bytes(4))
    width: int = pb.Int(4)
    height: int = pb.Int(4)


def test_parse_into_instance():
    header = PNGHeader.parse(PNG)
    assert isinstance(header, PNGHeader)
    assert (header.width, header.height) == (602, 172)
    assert dataclasses.is_dataclass(header)
    assert header.build() == PNG
    assert PNGHeader.sizeof() == len(PNG)


def test_construct_instance_with_defaults():
    header = PNGHeader(ihdr_size=13, width=602, height=172)
    assert header.magic == b"\x89PNG\r\n\x1a\n"
    assert header.build() == PNG
    with pytest.raises(TypeError):
        PNGHeader(13, 602, 172)
    with pytest.raises(TypeError):
        PNGHeader(width=1)


def test_annotations_and_field_order():
    names = [f.name for f in dataclasses.fields(PNGHeader)]
    assert names == ["magic", "ihdr_size", "ihdr_id", "width", "height"]
    assert dataclasses.fields(PNGHeader)[3].type is int


def test_inheritance_and_nesting():
    class Base(pb.Struct, endian="big"):
        a = pb.Int(2)

    class Child(Base):
        b = pb.Int(2)
        total = pb.Computed(lambda ctx: ctx.a + ctx.b)

    child = Child.parse(b"\x00\x01\x00\x02")
    assert (child.a, child.b, child.total) == (1, 2, 3)
    assert Child(a=1, b=2).build() == b"\x00\x01\x00\x02"

    class Outer(pb.Struct):
        n = pb.u8
        inner = Child.construct()

    outer = Outer.parse(b"\x05\x00\x01\x00\x02")
    assert isinstance(outer.inner, Child) and outer.inner.total == 3
    assert outer.build() == b"\x05\x00\x01\x00\x02"
    assert Outer(n=5, inner={"a": 1, "b": 2}).build() == b"\x05\x00\x01\x00\x02"
    assert Outer.sizeof() == 5


def test_to_and_from_dict():
    header = PNGHeader.parse(PNG)
    assert header.to_dict()["width"] == 602
    assert PNGHeader.from_dict(header.to_dict()) == header
