import pickle

import pytest

import pabo as pb


def test_hierarchy():
    for cls in (pb.StreamError, pb.SizeofError, pb.ValidationError, pb.ContextError):
        assert issubclass(cls, pb.PaboError)
    assert issubclass(pb.ConstError, pb.ValidationError)


def test_message_format():
    error = pb.PaboError("SOMETHING BROKE.")
    assert str(error) == "바보! SOMETHING BROKE. ABORT."
    error.path = ["a", "b", "[2]", "c"]
    error.offset = 7
    assert error.where == "a.b[2].c"
    assert str(error) == "바보! SOMETHING BROKE. (AT a.b[2].c, OFFSET 7) ABORT."


def test_pickle_keeps_location():
    error = pb.StreamError("x")
    error.path, error.offset = ["a"], 3
    copy = pickle.loads(pickle.dumps(error))
    assert type(copy) is pb.StreamError
    assert copy.path == ["a"] and copy.offset == 3


def test_errors_carry_field_path_and_offset():
    spec = pb.Spec(
        {
            "magic": pb.Const(b"PB", pb.Bytes(2)),
            "header": pb.Spec({"n": pb.Int(1), "sizes": pb.Repeat(pb.Int(2), 3)}),
        }
    )
    with pytest.raises(pb.StreamError) as info:
        spec.parse(b"PB\x03\x01\x00\x02\x00\x03")
    assert info.value.path == ["header", "sizes", "[2]"]
    assert info.value.offset == 7
    assert "header.sizes[2]" in str(info.value)

    with pytest.raises(pb.ConstError) as info:
        spec.parse(b"XX")
    assert info.value.where == "magic" and info.value.offset == 0


def test_build_errors_carry_field_path():
    spec = pb.Spec({"a": pb.Int(1), "b": pb.Seq([pb.Int(1), pb.Int(1)])})
    with pytest.raises(pb.ValidationError) as info:
        spec.build({"a": 1, "b": [1, 300]})
    assert info.value.where == "b[1]"
