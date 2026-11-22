import pabo as pb


def test_aliases():
    assert pb.u16be.build(1) == b"\x00\x01"
    assert pb.i32le.build(-1) == b"\xff" * 4
    assert pb.u24be.size == 3
    assert pb.f64.size == 8
    assert pb.u128.size == 16
    assert pb.f16be.build(1.5) == b"\x3e\x00"


def test_unsuffixed_aliases_inherit_endianness():
    spec = pb.Spec({"a": pb.u16, "b": pb.u16le}, endian="big")
    assert spec.build({"a": 1, "b": 1}) == b"\x00\x01\x01\x00"


def test_docs_do_not_mutate_shared_aliases():
    documented = pb.u32 / "count"
    assert documented.docs == "count" and pb.u32.docs == ""


def test_all_aliases_exported():
    assert set(pb.aliases.__all__) <= set(pb.__all__)
    assert "u8" in pb.aliases.__all__ and "f32be" in pb.aliases.__all__
