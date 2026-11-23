import pytest
from beartype.roar import BeartypeCallHintParamViolation
from hypothesis import given
from hypothesis import strategies as st

import pabo as pb


def test_cstring():
    """
    `CString` builds with a null terminator, parses up to the first null, and raises
    `PaboError` when the terminator is missing.
    """
    c = pb.CString()
    assert c.build("hi") == b"hi\x00"
    assert c.parse(b"hi\x00rest") == "hi"
    with pytest.raises(pb.PaboError):
        c.parse(b"no terminator")


@pytest.mark.parametrize("code", ["utf-8", "utf-16", "utf-16-le", "utf-32"])
def test_cstring_encodings(code):
    """
    `CString` round-trips non-ASCII text and stops at its terminator, for each of
    several UTF encodings (the parameter varied).
    """
    c = pb.CString(code)
    raw = c.build("héllo")
    assert c.parse(raw + b"rest") == "héllo"


def test_cstring_utf16_terminator():
    """
    In UTF-16 a `CString` terminator is a two-byte null, and a null high byte inside
    a character does not end the string.
    """
    assert pb.CString("utf-16-le").build("A") == b"A\x00\x00\x00"
    assert pb.CString("utf-16-le").parse(b"A\x00\x00\x00") == "A"


def test_pascal_string():
    """
    `PascalString` writes the encoded length with its prefix construct, then the
    text, and parses it back.
    """
    c = pb.PascalString(pb.Int(1))
    assert c.build("hi") == b"\x02hi"
    assert c.parse(b"\x02hi") == "hi"


def test_padded_string():
    """
    `PaddedString` pads short text with nulls up to its fixed length, and strips
    the padding when parsing.
    """
    c = pb.PaddedString(5)
    assert c.build("ab") == b"ab\x00\x00\x00"
    assert c.parse(b"ab\x00\x00\x00") == "ab"


def test_padded_string_validation_and_utf16():
    """
    `PaddedString` raises `PaboError` when the encoded text is longer than its
    length, and round-trips text in UTF-16.
    """
    with pytest.raises(pb.PaboError):
        pb.PaddedString(2).build("abc")
    c = pb.PaddedString(5, "utf-16-le")
    assert c.parse(c.build("A")) == "A"


def test_line_build():
    """
    `Line` builds text followed by a CRLF.
    """
    assert pb.Line().build("hi") == b"hi\r\n"


def test_line_parse():
    """
    `Line` parses up to the first CRLF and drops it.
    """
    assert pb.Line().parse(b"hi\r\nrest") == "hi"


@pytest.mark.parametrize("code", ["utf-8", "utf-16"])
def test_line_roundtrip(code):
    """
    `Line` parses only the first of two built lines, in UTF-8 and UTF-16 (the
    parameter varied).
    """
    c = pb.Line(code)
    assert c.parse(c.build("hello") + c.build("next")) == "hello"


def test_line_errors():
    """
    `Line` raises `PaboError` when parsing data with no CRLF, and when building text
    that contains a CRLF.
    """
    with pytest.raises(pb.PaboError):
        pb.Line().parse(b"no crlf")
    with pytest.raises(pb.PaboError):
        pb.Line().build("a\r\nb")


@pytest.mark.parametrize(
    "make",
    [
        lambda: pb.CString("klingon"),
        lambda: pb.PascalString(pb.u8, "klingon"),
        lambda: pb.PaddedString(4, "klingon"),
        lambda: pb.GreedyString("klingon"),
        lambda: pb.Line("klingon"),
    ],
)
def test_unknown_encoding(make):
    """
    Every string construct (the parameter varied) rejects an unknown encoding when
    it is created, with `PaboError` or a beartype violation.
    """
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        make()


def test_greedy_string():
    """
    `GreedyString` parses and builds all the remaining data, has no fixed size
    (`SizeofError`), and raises `ValidationError` on bytes that cannot be decoded.
    """
    c = pb.GreedyString()
    assert c.parse("héllo".encode()) == "héllo"
    assert c.build("héllo") == "héllo".encode()
    with pytest.raises(pb.SizeofError):
        c.size
    with pytest.raises(pb.ValidationError):
        c.parse(b"\xff")


def test_padded_string_pad_and_side():
    """
    `PaddedString` honours a custom `pad` character and left-side padding, and
    rejects a multi-character pad or an invalid side.
    """
    c = pb.PaddedString(5, pad=" ")
    assert c.build("ab") == b"ab   "
    assert c.parse(b"ab   ") == "ab"
    c = pb.PaddedString(5, pad=" ", side="left")
    assert c.build("ab") == b"   ab"
    assert c.parse(b"   ab") == "ab"
    c = pb.PaddedString(5, "utf-16-le", side="left")
    assert c.parse(c.build("A")) == "A"
    with pytest.raises(pb.PaboError):
        pb.PaddedString(5, pad="ab")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.PaddedString(5, side="middle")


text = st.text(st.characters(blacklist_categories=["Cs"]))
no_nulls = st.text(
    st.characters(blacklist_categories=["Cs"], blacklist_characters="\x00")
)


@given(no_nulls, st.sampled_from(["utf-8", "utf-16-le", "utf-16-be", "utf-32-le"]))
def test_cstring_roundtrip_property(value, code):
    """
    For any text without nulls and each sampled encoding, a built `CString`
    parses back to the same text, even with trailing data.
    """
    c = pb.CString(code)
    assert c.parse(c.build(value) + b"rest") == value


@given(text, st.sampled_from(["utf-8", "utf-16-le"]))
def test_pascal_string_roundtrip_property(value, code):
    """
    For any text and each sampled encoding, a `PascalString` with a four-byte
    length prefix round-trips.
    """
    c = pb.PascalString(pb.Int(4), code)
    assert c.parse(c.build(value)) == value


@given(no_nulls.filter(lambda s: len(s.encode()) <= 32))
def test_padded_string_roundtrip_property(value):
    """
    Any text without nulls that encodes to at most 32 bytes round-trips through a
    32-byte `PaddedString`.
    """
    c = pb.PaddedString(32)
    assert c.parse(c.build(value)) == value


@given(text.filter(lambda s: "\r\n" not in s and not s.endswith("\r")))
def test_line_roundtrip_property(value):
    """
    Any text with no CRLF (and not ending in a carriage return) round-trips through
    `Line`.
    """
    c = pb.Line()
    assert c.parse(c.build(value)) == value
