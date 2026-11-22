import pickle

import pytest

import pabo as pb
from pabo.context import evaluate


def test_container_attribute_access():
    c = pb.Container(a=1)
    assert c.a == c["a"] == 1
    c.b = 2
    assert c == {"a": 1, "b": 2}
    del c.b
    assert "b" not in c
    with pytest.raises(AttributeError):
        c.missing
    c._hidden = 3
    assert "_hidden" not in c and c._hidden == 3


def test_container_pickles():
    c = pb.Container(a=1)
    assert pickle.loads(pickle.dumps(c)) == c


def test_context_parent_and_settings():
    root = pb.Context({"x": 1})
    root._endian = "big"
    child = pb.Context({"y": 2}, parent=root)
    assert child._ is root
    assert child._root is root
    assert child.setting("_endian") == "big"
    assert child.setting("_missing", "default") == "default"


def test_this_resolution():
    root = pb.Context({"n": 3, "sub": {"m": 4}})
    child = pb.Context({"k": 5}, parent=root)
    assert pb.this.k(child) == 5
    assert pb.this._.n(child) == 3
    assert pb.this._root.sub.m(child) == 4
    assert pb.this["k"](child) == 5
    assert repr(pb.this._.n) == "this._.n"
    assert pb.this.a == pb.this.a and pb.this.a != pb.this.b
    with pytest.raises(pb.ContextError):
        pb.this.missing(child)
    with pytest.raises(pb.ContextError):
        pb.this._._.n(child)
    with pytest.raises(AttributeError):
        pb.this.x = 1


def test_evaluate():
    ctx = pb.Context({"n": 2})
    assert evaluate(5, ctx) == 5
    assert evaluate(lambda c: c.n * 2, ctx) == 4
    with pytest.raises(pb.ContextError):
        evaluate(lambda c: c.missing, ctx)


def test_parse_returns_container():
    data = pb.Spec({"a": pb.Int(1)}).parse(b"\x07")
    assert isinstance(data, pb.Container) and data.a == 7
