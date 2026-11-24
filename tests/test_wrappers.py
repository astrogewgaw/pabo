import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


def test_sequential():
    """
    `Seq` parses and builds a list with one value per construct, in order, and its
    length is the number of constructs.
    """
    c = pb.Seq([pb.Int(1), pb.Flag()])
    assert c.parse(b"\x05\x01") == [5, True]
    assert c.build([5, True]) == b"\x05\x01"
    assert len(c) == 2


def test_repeat():
    """
    `Repeat` parses and builds a fixed number of elements, has a size of count
    times the element size, and raises `PaboError` when building too few elements.
    """
    c = pb.Repeat(pb.Int(2), 2)
    assert c.parse(b"\x01\x00\x02\x00") == [1, 2]
    assert c.build([1, 2]) == b"\x01\x00\x02\x00"
    assert c.size == 4
    with pytest.raises(pb.PaboError):
        c.build([1])


def test_adapted():
    """
    `Adapted` applies `decode` to parsed values and `encode` to values before
    building them.
    """
    c = pb.Adapted(pb.Int(1), decode=lambda x: x * 2, encode=lambda x: x // 2)
    assert c.parse(b"\x03") == 6
    assert c.build(6) == b"\x03"


def test_prefixed():
    """
    `Prefixed` writes the byte length of the built data in its prefix, and parses
    exactly that many bytes, leaving the rest of the stream alone.
    """
    c = pb.Prefixed(pb.Int(2), pb.Bytes(-1))
    assert c.build(b"abc") == b"\x03\x00abc"
    assert c.parse(b"\x03\x00abcXYZ") == b"abc"


def test_greedy_over_bytes():
    """
    `Greedy` collects elements until one fails, here a `Const` that stops matching
    at the third byte.
    """
    c = pb.Greedy(pb.Const(b"A", pb.Bytes(1)))
    assert c.parse(b"AAB") == [b"A", b"A"]


def test_greedy_over_int():
    """
    `Greedy` over `Int` parses integers until the data runs out.
    """
    assert pb.Greedy(pb.Int(2)).parse(b"\x01\x00\x02\x00") == [1, 2]


def test_greedy_rewinds_after_partial_element():
    """
    `Greedy` stops at an element that cannot be read in full and rewinds the stream
    to where that element began, so its bytes are left unread.
    """
    from io import BytesIO

    stream = BytesIO(b"\x01\x00\x02\x00\x03")
    assert pb.Greedy(pb.Int(2)).parse(stream) == [1, 2]
    assert stream.read() == b"\x03"


def test_greedy_has_no_size():
    """
    `Greedy` has no fixed size, so asking for `size` raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        pb.Greedy(pb.Int(2)).size


def test_sequential_length_mismatch():
    """
    Building a `Seq` from a list with fewer values than constructs raises
    `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        pb.Seq([pb.Int(1), pb.Int(1)]).build([1])


def test_prefixed_counts_bytes_not_elements():
    """
    The `Prefixed` prefix holds the payload length in bytes, not the number of
    array elements, and `Prefixed` has no fixed size.
    """
    c = pb.Prefixed(pb.Int(1), pb.Array(pb.Int(4)))
    raw = c.build([1, 2])
    assert raw[0] == 8
    assert list(c.parse(raw)) == [1, 2]
    with pytest.raises(pb.PaboError):
        c.size


def test_padded_keeps_trailing_nulls():
    """
    `Padded` skips exactly its padding when parsing, so null bytes that belong to
    the wrapped data are kept, and its size includes the padding.
    """
    c = pb.Padded(2, pb.Bytes(3))
    assert c.build(b"a\x00\x00") == b"a\x00\x00\x00\x00"
    assert c.parse(b"a\x00\x00\x00\x00") == b"a\x00\x00"
    assert c.size == 5


def test_const_parse():
    """
    `Const` parses its expected value and raises `PaboError` when the data differs.
    """
    c = pb.Const(b"AB", pb.Bytes(2))
    assert c.parse(b"AB") == b"AB"
    with pytest.raises(pb.PaboError):
        c.parse(b"XY")


def test_const_build():
    """
    `Const` builds its value when given nothing or the same value, and raises
    `PaboError` when given a different value.
    """
    c = pb.Const(b"AB", pb.Bytes(2))
    assert c.build() == b"AB"
    assert c.build(b"AB") == b"AB"
    with pytest.raises(pb.PaboError):
        c.build(b"XY")


def test_padded_fill_and_side():
    """
    `Padded` uses a custom `fill` byte and left-side padding, and rejects a
    multi-byte fill or an invalid side.
    """
    c = pb.Padded(2, pb.Int(1), fill=b"\xff", side="left")
    assert c.build(1) == b"\xff\xff\x01"
    assert c.parse(b"\xff\xff\x01") == 1
    assert pb.Padded(1, pb.Int(1), fill=b" ").build(1) == b"\x01 "
    with pytest.raises(pb.PaboError):
        pb.Padded(1, pb.Int(1), fill=b"ab")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Padded(1, pb.Int(1), side="up")


def test_repeat_of_fixed_spec_parses_in_bulk(monkeypatch):
    """
    `Repeat` of a fixed-size `Spec` parses all its records in one bulk call (not
    record by record), returning `Container`s with the right values; a short read
    falls back to the slow path and raises `StreamError` with the missing field.
    """
    record = pb.Spec({"a": pb.u16, "b": pb.f32})
    raw = b"".join(record.build({"a": i, "b": i / 2}) for i in range(5))
    calls = []
    slow = pb.Specification._parse
    monkeypatch.setattr(
        pb.Specification,
        "_parse",
        lambda self, stream, ctx: calls.append(1) or slow(self, stream, ctx),
    )
    data = pb.Repeat(record, 5).parse(raw)
    assert calls == []
    assert [d.a for d in data] == list(range(5))
    assert all(isinstance(d, pb.Container) for d in data)
    with pytest.raises(pb.StreamError) as info:
        pb.Repeat(record, 6).parse(raw)
    assert info.value.where == "[5].a"


def test_prefixed_varint_length():
    """
    `Prefixed` accepts a variable-length prefix such as `VarInt`, in both orders.
    """

    c = pb.Prefixed(pb.VarInt(), pb.GreedyBytes())
    assert c.build(b"testing") == b"\x07testing"
    assert c.parse(b"\x07testing") == b"testing"
    long = pb.Prefixed(pb.VarInt(order="big"), pb.GreedyBytes())
    assert long.build(b"x" * 200)[:2] == b"\x81\x48"
    assert long.parse(long.build(b"x" * 200)) == b"x" * 200


def test_prefixed_rejects_a_length_that_is_not_an_int():
    """
    A prefix that parses into something other than a non-negative int (here a
    float) raises a `ValidationError` instead of failing inside the read.
    """

    with pytest.raises(pb.ValidationError, match="NON-NEGATIVE INT"):
        pb.Prefixed(pb.f32, pb.GreedyBytes()).parse(b"\x00\x00\x80\x3fa")


def test_adapted_errors_become_validation_errors():
    """
    Exceptions raised by `Adapted`'s decode and encode functions become
    `ValidationError`s that name the function, the value and the field.
    """

    def decode(value):
        """
        Fail on zero.
        """

        return 10 // value

    c = pb.Spec({"x": pb.Adapted(pb.u8, decode, lambda v: 10 // v)})
    with pytest.raises(pb.ValidationError) as info:
        c.parse(b"\x00")
    assert "decode FAILED ON 0" in str(info.value) and info.value.where == "x"
    assert isinstance(info.value.__cause__, ZeroDivisionError)
    with pytest.raises(pb.ValidationError, match="<lambda> FAILED ON 'a'"):
        c.build({"x": "a"})


def test_greedy_stops_when_an_adapter_fails():
    """
    `Greedy` stops at an element whose `Adapted` decode fails, just as at any
    other `PaboError`, and rewinds to before it.
    """

    digit = pb.Adapted(pb.Bytes(1), lambda raw: int(raw.decode()), str)
    c = pb.Seq([pb.Greedy(digit), pb.GreedyBytes()])
    assert c.parse(b"123x5") == [[1, 2, 3], b"x5"]


def test_delimited_bytes_and_strings():
    """
    `Delimited` reads up to a terminator of any length, parses what came before
    it, and moves past it; it builds the data followed by the terminator.
    """

    line = pb.Delimited(pb.GreedyString("ascii"), term=b";")
    spec = pb.Spec({"a": line, "b": line, "rest": pb.GreedyBytes()})
    assert spec.parse(b"hello;world;!") == {"a": "hello", "b": "world", "rest": b"!"}
    assert spec.build({"a": "hello", "b": "world", "rest": b"!"}) == b"hello;world;!"
    crlf = pb.Delimited(pb.GreedyBytes(), term=b"\r\n")
    assert crlf.parse(b"one\r\ntwo") == b"one"
    long = b"x" * 10000 + b"END"
    assert (
        pb.Delimited(pb.GreedyBytes(), term=b"END").parse(long + b"tail")
        == b"x" * 10000
    )


def test_delimited_options():
    """
    `include` keeps the terminator, `consume=False` leaves it for the next field,
    and `eos` accepts the end of the stream in its place.
    """

    keep = pb.Delimited(pb.GreedyBytes(), term=b"\n", include=True)
    assert keep.parse(b"a\nb") == b"a\n"
    assert keep.build(b"a\n") == b"a\n"
    leave = pb.Spec(
        {
            "a": pb.Delimited(pb.GreedyBytes(), term=b"|", consume=False),
            "sep": pb.Const(b"|", pb.Bytes(1)),
            "b": pb.GreedyBytes(),
        }
    )
    assert leave.parse(b"x|y") == {"a": b"x", "sep": b"|", "b": b"y"}
    assert leave.build({"a": b"x", "b": b"y"}) == b"x|y"
    lenient = pb.Delimited(pb.GreedyBytes(), term=b"\n", eos=True)
    assert lenient.parse(b"last line") == b"last line"


def test_delimited_errors():
    """
    A missing terminator, data containing it, data not ending with it (with
    `include`) and an empty terminator all raise.
    """

    c = pb.Delimited(pb.GreedyBytes(), term=b";")
    with pytest.raises(pb.StreamError, match="BEFORE THE TERMINATOR"):
        c.parse(b"no end")
    with pytest.raises(pb.ValidationError, match="CONTAINS THE TERMINATOR"):
        c.build(b"a;b")
    with pytest.raises(pb.ValidationError, match="MUST END WITH"):
        pb.Delimited(pb.GreedyBytes(), term=b";", include=True).build(b"ab")
    with pytest.raises(pb.PaboError):
        pb.Delimited(pb.GreedyBytes(), term=b"")
    with pytest.raises(pb.SizeofError):
        c.size


def test_delimited_on_a_stream_that_cannot_seek():
    """
    On a stream that can only read forwards, `Delimited` reads byte by byte, and
    refuses `consume=False`.
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

    c = pb.Delimited(pb.GreedyBytes(), term=b"\r\n")
    stream = Forward(b"ab\r\ncd")
    assert c.parse(stream) == b"ab" and stream.raw == b"cd"
    with pytest.raises(pb.StreamError, match="CANNOT SEEK"):
        pb.Delimited(pb.GreedyBytes(), term=b";", consume=False).parse(Forward(b"a;"))
