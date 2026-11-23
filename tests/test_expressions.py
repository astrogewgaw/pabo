import pytest

import pabo as pb
from pabo import lenof, this
from pabo.expressions import evaluate


@pytest.fixture
def ctx():
    """
    A child context with fields of its own, under a root context with others.
    """
    root = pb.Context({"n": 3, "sub": {"m": 4}, "items": [10, 20, 30]})
    return pb.Context({"k": 5, "data": b"abcd", "flags": 0b1010}, parent=root)


def test_this_resolution(ctx):
    """
    `this` references resolve fields in the current, parent (`_`) and root (`_root`)
    contexts, index into values, and raise `ContextError` for missing fields or
    parents. References cannot be assigned to.
    """
    assert this.k(ctx) == 5
    assert this._.n(ctx) == 3
    assert this._root.sub.m(ctx) == 4
    assert this["k"](ctx) == 5
    assert this._.items[1](ctx) == 20
    with pytest.raises(pb.ContextError):
        this.missing(ctx)
    with pytest.raises(pb.ContextError):
        this._._.n(ctx)
    with pytest.raises(pb.ContextError):
        this._.items[7](ctx)
    with pytest.raises(AttributeError):
        this.x = 1


@pytest.mark.parametrize(
    "expr, expected",
    [
        (this.k + 1, 6),
        (1 + this.k, 6),
        (this.k - 1, 4),
        (10 - this.k, 5),
        (this.k * this._.n, 15),
        (2 * this.k, 10),
        (this.k / 2, 2.5),
        (11 / this.k, 2.2),
        (this.k // 2, 2),
        (11 // this.k, 2),
        (this.k % 3, 2),
        (17 % this.k, 2),
        (this.k**2, 25),
        (2**this.k, 32),
        (this.k << 1, 10),
        (1 << this.k, 32),
        (this.k >> 1, 2),
        (64 >> this.k, 2),
        (this.flags & 0b10, 0b10),
        (0b11 & this.flags, 0b10),
        (this.flags | 1, 0b1011),
        (1 | this.flags, 0b1011),
        (this.flags ^ 0b1111, 0b0101),
        (0b1111 ^ this.flags, 0b0101),
        (-this.k, -5),
        (+this.k, 5),
        (~this.k, -6),
        (abs(-this.k), 5),
        (this.data[1:3], b"bc"),
        (lenof(this.data), 4),
        (lenof(this._.items) * 2, 6),
    ],
)
def test_arithmetic_and_bitwise(ctx, expr, expected):
    """
    Arithmetic, bitwise, unary operators, slicing and `lenof` build expressions
    (also with the expression on the right) that evaluate against the context.
    """
    assert isinstance(expr, pb.Expr)
    assert expr(ctx) == expected


@pytest.mark.parametrize(
    "expr, expected",
    [
        (this.k == 5, True),
        (this.k == 5, True),
        (this.k != 5, False),
        (this.k < 6, True),
        (this.k < 6, True),
        (this.k <= 5, True),
        (this.k > 5, False),
        (this.k >= this._.n, True),
        ((this.k == 5) & (this._.n == 3), True),
        ((this.k == 1) | (this._.n == 1), False),
    ],
)
def test_comparisons(ctx, expr, expected):
    """
    Comparisons (in either order) and their combination with `&` and `|` build
    expressions that evaluate to the expected booleans.
    """
    assert isinstance(expr, pb.Expr)
    assert expr(ctx) is expected


def test_expressions_have_no_truth_value():
    """
    `and`, `or`, `not`, `if` and chained comparisons need a truth value, so they
    raise a `TypeError` that explains what to use instead.
    """
    with pytest.raises(TypeError, match="NO TRUTH VALUE"):
        bool(this.k == 1)
    with pytest.raises(TypeError):
        (this.k == 1) and (this.n == 2)
    with pytest.raises(TypeError):
        not this.k
    with pytest.raises(TypeError):
        this.a == 1 & this.b == 2  # noqa: B015
    with pytest.raises(TypeError):
        list(this.k)


def test_repr():
    """
    Expressions print as the Python that built them.
    """
    assert repr(this._.n) == "this._.n"
    assert repr(this["a b"][0]) == "this['a b'][0]"
    assert repr(this.n * 2 + 1) == "((this.n * 2) + 1)"
    assert repr(-this.n) == "-this.n"
    assert repr(lenof(this.data)) == "len(this.data)"
    assert repr((this.k + 1)[0]) == "(this.k + 1)[0]"


def test_expressions_are_hashable():
    """
    Expressions hash by identity, so they can be used where a hashable is needed
    (for example as the key of a `Switch`).
    """
    expr = this.tag
    assert {expr: 1}[expr] == 1


def test_errors_while_evaluating(ctx):
    """
    An operator failing while evaluating (here, dividing by zero or taking the
    length of an int) raises `ContextError`, naming the expression.
    """
    with pytest.raises(pb.ContextError, match=r"\(this.k / 0\)"):
        (this.k / 0)(ctx)
    with pytest.raises(pb.ContextError, match="len"):
        lenof(this.k)(ctx)


def test_evaluate():
    """
    `evaluate()` returns constants as is, calls expressions and functions with the
    context, and turns a missing field lookup into `ContextError`.
    """
    ctx = pb.Context({"n": 2})
    assert evaluate(5, ctx) == 5
    assert evaluate(lambda c: c.n * 2, ctx) == 4
    assert evaluate(this.n * 2, ctx) == 4
    with pytest.raises(pb.ContextError):
        evaluate(lambda c: c.missing, ctx)


def test_expressions_in_specifications():
    """
    Expressions work as counts, lengths, conditions, keys and rebuilt values inside
    specifications, when parsing and when building.
    """
    spec = pb.Spec(
        {
            "n": pb.Rebuild(pb.u8, lenof(this.words)),
            "words": pb.Repeat(pb.u16, this.n),
            "stop": pb.StopIf(this.n == 0),
            "tagged": pb.Flag(),
            "body": pb.If(this.tagged & (this.n > 1), pb.Bytes(this.n * 2)),
            "kind": pb.Switch(this.n % 2, {0: pb.u8, 1: pb.u16}),
        },
        endian="little",
    )
    raw = b"\x02\x01\x00\x02\x00\x01abcd\x07"
    data = spec.parse(raw)
    assert data == {
        "n": 2,
        "words": [1, 2],
        "stop": None,
        "tagged": True,
        "body": b"abcd",
        "kind": 7,
    }
    assert (
        spec.build({"words": [1, 2], "tagged": True, "body": b"abcd", "kind": 7}) == raw
    )
    assert spec.parse(b"\x00") == {"n": 0, "words": []}
    assert spec.sizeof({"n": 2, "tagged": True}) == 1 + 4 + 1 + 4 + 1
