import pickle

import pytest

import pabo as pb
from pabo.context import evaluate


def test_container_attribute_access():
    """
    `Container` supports attribute get, set and delete for its keys, raises
    `AttributeError` for missing ones, and keeps underscore attributes out of the dict.
    """
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
    """
    A `Container` survives a pickle round-trip unchanged.
    """
    c = pb.Container(a=1)
    assert pickle.loads(pickle.dumps(c)) == c


def test_context_parent_and_settings():
    """
    A child `Context` exposes its parent as `_` and the top level as `_root`, and
    `setting()` looks names up the parent chain, falling back to a default.
    """
    root = pb.Context({"x": 1})
    root._endian = "big"
    child = pb.Context({"y": 2}, parent=root)
    assert child._ is root
    assert child._root is root
    assert child.setting("_endian") == "big"
    assert child.setting("_missing", "default") == "default"


def test_this_resolution():
    """
    `this` references resolve fields in the current, parent (`_`) and root (`_root`)
    contexts, compare by path, and raise `ContextError` for missing fields or parents.
    """
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
    """
    `evaluate()` returns constants as is, calls callables with the context, and turns a
    missing field lookup into `ContextError`.
    """
    ctx = pb.Context({"n": 2})
    assert evaluate(5, ctx) == 5
    assert evaluate(lambda c: c.n * 2, ctx) == 4
    with pytest.raises(pb.ContextError):
        evaluate(lambda c: c.missing, ctx)


def test_parse_returns_container():
    """
    Parsing a specification returns a `Container` with attribute access to fields.
    """
    data = pb.Spec({"a": pb.Int(1)}).parse(b"\x07")
    assert isinstance(data, pb.Container) and data.a == 7


def test_nested_plain_dicts_get_attribute_access():
    """
    Plain dicts stored in a `Container` also get attribute access.
    """
    c = pb.Container(inner={"x": 1})
    assert c.inner.x == 1
