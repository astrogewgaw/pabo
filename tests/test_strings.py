import pytest
from beartype.roar import BeartypeCallHintParamViolation
from hypothesis import given
from hypothesis import strategies as st

import pabo as pb


def test_cstring():
    c = pb.CString()
    assert c.build("hi") == b"hi\x00"
    assert c.parse(b"hi\x00rest") == "hi"
    with pytest.raises(pb.PaboError):
        c.parse(b"no terminator")


@pytest.mark.parametrize("code", ["utf-8", "utf-16", "utf-16-le", "utf-32"])
def test_cstring_encodings(code):
    c = pb.CString(code)
    raw = c.build("héllo")
    assert c.parse(raw + b"rest") == "héllo"


def test_cstring_utf16_terminator():
    assert pb.CString("utf-16-le").build("A") == b"A\x00\x00\x00"
    assert pb.CString("utf-16-le").parse(b"A\x00\x00\x00") == "A"


def test_pascal_string():
    c = pb.PascalString(pb.Int(1))
    assert c.build("hi") == b"\x02hi"
    assert c.parse(b"\x02hi") == "hi"


def test_padded_string():
    c = pb.PaddedString(5)
    assert c.build("ab") == b"ab\x00\x00\x00"
    assert c.parse(b"ab\x00\x00\x00") == "ab"


def test_padded_string_validation_and_utf16():
    with pytest.raises(pb.PaboError):
        pb.PaddedString(2).build("abc")
    c = pb.PaddedString(5, "utf-16-le")
    assert c.parse(c.build("A")) == "A"


def test_line_build():
    assert pb.Line().build("hi") == b"hi\r\n"


def test_line_parse():
    assert pb.Line().parse(b"hi\r\nrest") == "hi"


@pytest.mark.parametrize("code", ["utf-8", "utf-16"])
def test_line_roundtrip(code):
    c = pb.Line(code)
    assert c.parse(c.build("hello") + c.build("next")) == "hello"


def test_line_errors():
    with pytest.raises(pb.PaboError):
        pb.Line().parse(b"no crlf")
    with pytest.raises(pb.PaboError):
        pb.Line().build("a\r\nb")


def test_greedy_string():
    c = pb.GreedyString()
    assert c.parse("héllo".encode()) == "héllo"
    assert c.build("héllo") == "héllo".encode()
    with pytest.raises(pb.SizeofError):
        c.size
    with pytest.raises(pb.ValidationError):
        c.parse(b"\xff")


def test_padded_string_pad_and_side():
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
    c = pb.CString(code)
    assert c.parse(c.build(value) + b"rest") == value


@given(text, st.sampled_from(["utf-8", "utf-16-le"]))
def test_pascal_string_roundtrip_property(value, code):
    c = pb.PascalString(pb.Int(4), code)
    assert c.parse(c.build(value)) == value


@given(no_nulls.filter(lambda s: len(s.encode()) <= 32))
def test_padded_string_roundtrip_property(value):
    c = pb.PaddedString(32)
    assert c.parse(c.build(value)) == value


@given(text.filter(lambda s: "\r\n" not in s and not s.endswith("\r")))
def test_line_roundtrip_property(value):
    c = pb.Line()
    assert c.parse(c.build(value)) == value
