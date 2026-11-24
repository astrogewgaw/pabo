from io import BytesIO

import pytest

import pabo as pb
from pabo import this


def test_computed():
    """
    `Computed` derives a value from earlier fields when parsing, writes nothing and
    ignores any given value when building, takes no space, and accepts a constant.
    """
    spec = pb.Spec(
        {"w": pb.Int(1), "h": pb.Int(1), "area": pb.Computed(lambda c: c.w * c.h)}
    )
    assert spec.parse(b"\x02\x03") == {"w": 2, "h": 3, "area": 6}
    assert spec.build({"w": 2, "h": 3}) == b"\x02\x03"
    assert spec.build({"w": 2, "h": 3, "area": 99}) == b"\x02\x03"
    assert spec.size == 2
    assert pb.Computed(5).parse(b"") == 5


def test_rebuild_length_prefix():
    """
    `Rebuild` recomputes a length prefix from a later field when building,
    overriding any given value, and parses it as a normal field.
    """
    spec = pb.Spec(
        {
            "n": pb.Rebuild(pb.Int(1), lambda c: len(c.payload)),
            "payload": pb.Bytes(this.n),
        }
    )
    assert spec.build({"payload": b"abc"}) == b"\x03abc"
    assert spec.build({"n": 99, "payload": b"ab"}) == b"\x02ab"
    assert spec.parse(b"\x03abc") == {"n": 3, "payload": b"abc"}
    assert spec.build(spec.parse(b"\x03abc")) == b"\x03abc"


def test_if():
    """
    `If` parses or builds its construct only when the condition holds and gives None
    otherwise, raises `ValidationError` when a needed value is missing, and sizes by
    condition.
    """
    spec = pb.Spec({"has": pb.Flag(), "value": pb.If(this.has, pb.Int(2))})
    assert spec.parse(b"\x01\x05\x00") == {"has": True, "value": 5}
    assert spec.parse(b"\x00") == {"has": False, "value": None}
    assert spec.build({"has": False}) == b"\x00"
    assert spec.build({"has": True, "value": 5}) == b"\x01\x05\x00"
    with pytest.raises(pb.ValidationError):
        spec.build({"has": True})
    assert spec.sizeof({"has": True}) == 3
    assert spec.sizeof({"has": False}) == 1


def test_if_else():
    """
    `If` with an else branch picks between two constructs by condition, is not
    omittable, and raises `PaboError` when the value is missing.
    """
    c = pb.If(this.wide, pb.Int(2), pb.Int(1))
    spec = pb.Spec({"wide": pb.Flag(), "v": c})
    assert spec.parse(b"\x00\x07") == {"wide": False, "v": 7}
    assert spec.parse(b"\x01\x07\x00") == {"wide": True, "v": 7}
    assert not c._omittable()
    with pytest.raises(pb.PaboError):
        spec.build({"wide": True})


def test_optional():
    """
    `Optional` returns None and rewinds the stream when its construct fails, builds
    nothing from None, and has no fixed size (`SizeofError`).
    """
    c = pb.Optional(pb.Const(b"X", pb.Bytes(1)))
    stream = BytesIO(b"Y")
    assert c.parse(stream) is None and stream.tell() == 0
    assert c.parse(b"X") == b"X"
    assert c.build(None) == b""
    assert c.build(b"X") == b"X"
    with pytest.raises(pb.SizeofError):
        c.size


def test_switch():
    """
    `Switch` picks a construct by key and falls back to `default`, and without a
    default an unknown key raises `ValidationError` at the field path `body`.
    """
    spec = pb.Spec(
        {
            "tag": pb.Int(1),
            "body": pb.Switch(
                this.tag, {1: pb.Int(2), 2: pb.CString()}, default=pb.Bytes(1)
            ),
        }
    )
    assert spec.parse(b"\x01\x05\x00") == {"tag": 1, "body": 5}
    assert spec.parse(b"\x02hi\x00") == {"tag": 2, "body": "hi"}
    assert spec.parse(b"\x09z") == {"tag": 9, "body": b"z"}
    assert spec.build({"tag": 2, "body": "hi"}) == b"\x02hi\x00"
    assert spec.sizeof({"tag": 1}) == 3
    strict = pb.Spec({"tag": pb.Int(1), "body": pb.Switch(this.tag, {1: pb.Int(1)})})
    with pytest.raises(pb.ValidationError) as info:
        strict.parse(b"\x05\x00")
    assert info.value.where == "body"


def test_repeat_until():
    """
    `RepeatUntil` reads elements up to and including the first that meets the
    predicate, and raises on builds that never meet it, short reads and `size`.
    """
    c = pb.RepeatUntil(lambda x, ctx: x == 0, pb.Int(1))
    assert c.parse(b"\x03\x02\x00\x09") == [3, 2, 0]
    assert c.build([3, 2, 0]) == b"\x03\x02\x00"
    with pytest.raises(pb.ValidationError):
        c.build([1, 2])
    with pytest.raises(pb.StreamError) as info:
        c.parse(b"\x01\x02")
    assert info.value.where == "[2]"
    with pytest.raises(pb.SizeofError):
        c.size


def test_repeat_with_context_count():
    """
    `Repeat` can take its count from an earlier field via `this`.
    """
    spec = pb.Spec({"n": pb.Int(1), "xs": pb.Repeat(pb.Int(1), this.n)})
    assert spec.parse(b"\x02\x07\x08") == {"n": 2, "xs": [7, 8]}


def test_stop_if():
    """
    `StopIf` ends a `Spec` or `Seq` early when its condition holds, leaving out the
    fields after it, and does nothing otherwise.
    """
    spec = pb.Spec(
        {"n": pb.Int(1), "stop": pb.StopIf(lambda c: c.n == 0), "x": pb.Int(1)}
    )
    assert spec.parse(b"\x00") == {"n": 0}
    assert spec.parse(b"\x01\x05") == {"n": 1, "stop": None, "x": 5}
    assert spec.build({"n": 0}) == b"\x00"
    assert spec.build({"n": 1, "x": 5}) == b"\x01\x05"
    seq = pb.Seq([pb.Int(1), pb.StopIf(True), pb.Int(1)])
    assert seq.parse(b"\x01\x02") == [1]


def test_terminated():
    """
    `Terminated` parses only at the end of the stream, raising `StreamError` when
    data remains, and builds nothing.
    """
    spec = pb.Spec({"a": pb.Int(1), "end": pb.Terminated()})
    assert spec.parse(b"\x01") == {"a": 1, "end": None}
    with pytest.raises(pb.StreamError):
        spec.parse(b"\x01\x02")
    assert spec.build({"a": 1}) == b"\x01"


def test_check():
    """
    `Check` raises `ValidationError` with its message when its condition on earlier
    fields fails, both when parsing and when building.
    """
    spec = pb.Spec(
        {
            "lo": pb.Int(1),
            "hi": pb.Int(1),
            "ok": pb.Check(lambda c: c.lo <= c.hi, message="lo must not exceed hi."),
        }
    )
    assert spec.parse(b"\x01\x02")["hi"] == 2
    with pytest.raises(pb.ValidationError, match="lo must not exceed hi"):
        spec.parse(b"\x02\x01")
    with pytest.raises(pb.ValidationError):
        spec.build({"lo": 2, "hi": 1})


def test_validated():
    """
    `Validated` raises `ValidationError` when a parsed or built value fails the
    predicate, and keeps the size of the wrapped construct.
    """
    c = pb.Validated(pb.Int(1), lambda v, ctx: v < 10)
    assert c.parse(b"\x05") == 5
    with pytest.raises(pb.ValidationError):
        c.parse(b"\x0b")
    with pytest.raises(pb.ValidationError):
        c.build(11)
    assert c.size == 1


def test_failing_predicates_raise_validation_errors():
    """
    A `RepeatUntil` or `Validated` predicate that raises gives a
    `ValidationError`, when parsing and when building.
    """

    until = pb.RepeatUntil(lambda e, ctx: 1 // e, pb.u8)
    with pytest.raises(pb.ValidationError, match="ZeroDivisionError"):
        until.parse(b"\x00")
    with pytest.raises(pb.ValidationError, match="ZeroDivisionError"):
        until.build([0])
    valid = pb.Validated(pb.u8, lambda v, ctx: v.startswith("a"))
    with pytest.raises(pb.ValidationError, match="AttributeError"):
        valid.parse(b"\x01")


def test_union_parses_every_view_of_the_same_bytes():
    """
    A `Union` parses each field from the same start, moves past the longest, and
    builds the first field given, padded to the largest size.
    """

    union = pb.Union({"word": pb.u32, "half": pb.u16, "bytes": pb.Bytes(4)})
    spec = pb.Spec({"u": union, "next": pb.u8})
    data = spec.parse(b"\x01\x02\x03\x04\x05")
    assert data.u == {"word": 0x04030201, "half": 0x0201, "bytes": b"\x01\x02\x03\x04"}
    assert data.next == 5
    assert union.size == 4
    assert union.build({"half": 0x0201}) == b"\x01\x02\x00\x00"
    assert union.build({"word": 1, "half": None}) == b"\x01\x00\x00\x00"
    with pytest.raises(pb.ValidationError, match="NONE OF THE FIELDS"):
        union.build({})
    with pytest.raises(pb.PaboError):
        pb.Union({})


def test_union_fields_can_refer_to_earlier_ones():
    """
    A field of a `Union` can depend on a field before it, and a union of fields
    of varying size moves past the longest one actually parsed.
    """

    union = pb.Union({"n": pb.u8, "text": pb.PascalString(pb.u8, "ascii")})
    data = pb.Spec({"u": union, "rest": pb.GreedyBytes()}).parse(b"\x02hi!")
    assert data == {"u": {"n": 2, "text": "hi"}, "rest": b"!"}
    with pytest.raises(pb.SizeofError):
        union.size


def test_select_takes_the_first_alternative_that_works():
    """
    `Select` returns the first alternative that parses, rewinding after each that
    fails, builds with the first that accepts the value, and reports every
    failure when none works.
    """

    magic = pb.Const(b"PB", pb.Bytes(2))
    c = pb.Select([magic, pb.u16])
    assert c.parse(b"PB") == b"PB"
    assert c.parse(b"\x01\x00") == 1
    assert c.build(b"PB") == b"PB" and c.build(7) == b"\x07\x00"
    assert c.size == 2
    s = pb.Select([pb.Const(b"A", pb.Bytes(1)), pb.Const(b"B", pb.Bytes(1))])
    with pytest.raises(pb.ValidationError, match="NO ALTERNATIVE WORKED") as info:
        s.parse(b"C")
    assert "0:" in str(info.value) and "1:" in str(info.value)
    with pytest.raises(pb.SizeofError):
        pb.Select([pb.u8, pb.u16]).size
    with pytest.raises(pb.PaboError):
        pb.Select([])


def test_deferred_recursive_layout():
    """
    `Deferred` lets a construct contain itself: a tree whose nodes hold a count of
    children parses and builds to any depth.
    """

    node = pb.Spec(
        {
            "value": pb.u8,
            "count": pb.Rebuild(pb.u8, pb.lenof(this.children)),
            "children": pb.Repeat(pb.Deferred(lambda ctx: node), this.count),
        }
    )
    tree = {
        "value": 1,
        "children": [
            {"value": 2, "children": []},
            {"value": 3, "children": [{"value": 4, "children": []}]},
        ],
    }
    raw = node.build(tree)
    assert raw == bytes([1, 2, 2, 0, 3, 1, 4, 0])
    parsed = node.parse(raw)
    assert parsed.children[1].children[0].value == 4


def test_deferred_layout_from_earlier_data():
    """
    `Deferred` can choose a construct from fields parsed before it, its size
    follows the choice, and a function that doesn't return a construct raises.
    """

    kinds = {1: pb.u8, 2: pb.u16}
    spec = pb.Spec({"kind": pb.u8, "value": pb.Deferred(lambda ctx: kinds[ctx.kind])})
    assert spec.parse(b"\x02\x01\x01") == {"kind": 2, "value": 257}
    assert spec.build({"kind": 1, "value": 5}) == b"\x01\x05"
    assert spec.sizeof({"kind": 2}) == 3
    with pytest.raises(pb.ValidationError, match="MUST RETURN A CONSTRUCT"):
        pb.Deferred(lambda ctx: 42).parse(b"\x00")
    with pytest.raises(pb.ContextError, match="KeyError"):
        spec.parse(b"\x07\x00")
