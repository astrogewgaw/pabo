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
