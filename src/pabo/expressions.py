"""
Expressions over the context: `this.length`, `this.n * 2`, `this.kind == 3`, ...

An expression is evaluated later, with the context of the field that uses it.
`this.name` refers to a field of the current specification, `this._.name` to a
field of the enclosing one, and `this._root.name` to one at the top level.
Arithmetic, bitwise operators, comparisons and indexing on an expression give
another expression:

    pb.Bytes(this.length * 2)
    pb.StopIf(this.count == 0)
    pb.If((this.flags & 0x80) != 0, pb.u32)
    pb.Rebuild(pb.u16, lenof(this.payload))

Python's `and`, `or` and `not` (and `if`) cannot be overloaded, so they raise a
`TypeError` on an expression: use `&`, `|` and `== 0` instead, with parentheses
(`(this.a == 1) & (this.b == 2)`), or write a function of the context:
`lambda ctx: ctx.a == 1 and ctx.b == 2`. Functions of the context work wherever
an expression does.
"""

import operator
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, no_type_check

from pabo.errors import ContextError, PaboError

if TYPE_CHECKING:
    from pabo.context import Context


class Expr:
    """
    Base class for expressions: callables that compute a value from the context.

    Operators on an expression build a bigger expression instead of computing
    anything, so `==` does not compare expressions and an expression has no
    truth value.
    """

    __slots__ = ()

    def __call__(self, ctx: "Context") -> Any:
        raise NotImplementedError

    def __bool__(self) -> bool:
        raise TypeError(
            f"{self!r} IS AN EXPRESSION, EVALUATED LATER, SO IT HAS NO TRUTH VALUE. "
            "USE & | INSTEAD OF and/or, == 0 INSTEAD OF not, PARENTHESES AROUND "
            "COMPARISONS, OR A FUNCTION OF THE CONTEXT (lambda ctx: ...)."
        )

    # Expressions are used as keys and in sets by identity; `==` builds an expression.
    __hash__ = object.__hash__

    def __iter__(self):
        raise TypeError(f"{self!r} IS AN EXPRESSION, SO IT CANNOT BE ITERATED.")

    def __getitem__(self, key: Any) -> "Expr":
        return Binary(operator.getitem, "[]", self, key)

    # Arithmetic and bitwise operators, in both directions.
    def __add__(self, other: Any) -> "Expr":
        return Binary(operator.add, "+", self, other)

    def __radd__(self, other: Any) -> "Expr":
        return Binary(operator.add, "+", other, self)

    def __sub__(self, other: Any) -> "Expr":
        return Binary(operator.sub, "-", self, other)

    def __rsub__(self, other: Any) -> "Expr":
        return Binary(operator.sub, "-", other, self)

    def __mul__(self, other: Any) -> "Expr":
        return Binary(operator.mul, "*", self, other)

    def __rmul__(self, other: Any) -> "Expr":
        return Binary(operator.mul, "*", other, self)

    def __truediv__(self, other: Any) -> "Expr":
        return Binary(operator.truediv, "/", self, other)

    def __rtruediv__(self, other: Any) -> "Expr":
        return Binary(operator.truediv, "/", other, self)

    def __floordiv__(self, other: Any) -> "Expr":
        return Binary(operator.floordiv, "//", self, other)

    def __rfloordiv__(self, other: Any) -> "Expr":
        return Binary(operator.floordiv, "//", other, self)

    def __mod__(self, other: Any) -> "Expr":
        return Binary(operator.mod, "%", self, other)

    def __rmod__(self, other: Any) -> "Expr":
        return Binary(operator.mod, "%", other, self)

    def __pow__(self, other: Any) -> "Expr":
        return Binary(operator.pow, "**", self, other)

    def __rpow__(self, other: Any) -> "Expr":
        return Binary(operator.pow, "**", other, self)

    def __lshift__(self, other: Any) -> "Expr":
        return Binary(operator.lshift, "<<", self, other)

    def __rlshift__(self, other: Any) -> "Expr":
        return Binary(operator.lshift, "<<", other, self)

    def __rshift__(self, other: Any) -> "Expr":
        return Binary(operator.rshift, ">>", self, other)

    def __rrshift__(self, other: Any) -> "Expr":
        return Binary(operator.rshift, ">>", other, self)

    def __and__(self, other: Any) -> "Expr":
        return Binary(operator.and_, "&", self, other)

    def __rand__(self, other: Any) -> "Expr":
        return Binary(operator.and_, "&", other, self)

    def __or__(self, other: Any) -> "Expr":
        return Binary(operator.or_, "|", self, other)

    def __ror__(self, other: Any) -> "Expr":
        return Binary(operator.or_, "|", other, self)

    def __xor__(self, other: Any) -> "Expr":
        return Binary(operator.xor, "^", self, other)

    def __rxor__(self, other: Any) -> "Expr":
        return Binary(operator.xor, "^", other, self)

    # Comparisons. Python swaps these itself for reflected cases (`0 == this.n`).
    def __eq__(self, other: Any) -> "Expr":  # type: ignore[override]
        return Binary(operator.eq, "==", self, other)

    def __ne__(self, other: Any) -> "Expr":  # type: ignore[override]
        return Binary(operator.ne, "!=", self, other)

    def __lt__(self, other: Any) -> "Expr":
        return Binary(operator.lt, "<", self, other)

    def __le__(self, other: Any) -> "Expr":
        return Binary(operator.le, "<=", self, other)

    def __gt__(self, other: Any) -> "Expr":
        return Binary(operator.gt, ">", self, other)

    def __ge__(self, other: Any) -> "Expr":
        return Binary(operator.ge, ">=", self, other)

    # Unary operators.
    def __neg__(self) -> "Expr":
        return Unary(operator.neg, "-", self)

    def __pos__(self) -> "Expr":
        return Unary(operator.pos, "+", self)

    def __invert__(self) -> "Expr":
        return Unary(operator.invert, "~", self)

    def __abs__(self) -> "Expr":
        return Call(abs, (self,))


class This(Expr):
    """
    A reference to a field, such as `this.length` or `this._.header.size`.

    `this._` steps out to the enclosing specification's context and
    `this._root` to the outermost one. `this.items[0]` indexes into a parsed
    value. `this["name"]` reads a field whose name is not a valid attribute.
    """

    __slots__ = ("__path",)
    __path: tuple[Any, ...]

    def __init__(self, path: tuple[Any, ...] = ()):
        object.__setattr__(self, "_This__path", path)

    def __getattr__(self, name: str) -> "This":
        if name.startswith("__"):
            raise AttributeError(name)
        return This((*self.__path, name))

    def __getitem__(self, name: Any) -> "This":
        return This((*self.__path, name))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("REFERENCES ARE READ-ONLY.")

    # No runtime type check (see `context.py`): runs for every `this` reference,
    # once per field that uses one; the context always comes from pabo itself.
    @no_type_check
    def __call__(self, ctx: "Context") -> Any:
        value: Any = ctx
        for name in self.__path:
            try:
                if name == "_":
                    value = value._
                elif name == "_root":
                    value = value._root
                else:
                    value = value[name]
            except (KeyError, IndexError, AttributeError, TypeError):
                raise ContextError(f"CANNOT RESOLVE {self!r}.") from None
            if value is None and name in ("_", "_root"):
                raise ContextError(f"CANNOT RESOLVE {self!r}: THERE IS NO PARENT.")
        return value

    def __repr__(self) -> str:
        out = "this"
        for name in self.__path:
            if isinstance(name, str) and name.isidentifier():
                out += f".{name}"
            else:
                out += f"[{name!r}]"
        return out


class Binary(Expr):
    """
    Two operands combined by an operator, such as `this.n * 2`.
    """

    __slots__ = ("left", "op", "right", "symbol")

    def __init__(
        self, op: Callable[[Any, Any], Any], symbol: str, left: Any, right: Any
    ):
        self.op = op
        self.symbol = symbol
        self.left = left
        self.right = right

    @no_type_check
    def __call__(self, ctx: "Context") -> Any:
        left = evaluate(self.left, ctx)
        right = evaluate(self.right, ctx)
        try:
            return self.op(left, right)
        except Exception as error:
            raise ContextError(f"CANNOT EVALUATE {self!r}: {error!r}.") from error

    def __repr__(self) -> str:
        if self.symbol == "[]":
            return f"{self.left!r}[{self.right!r}]"
        return f"({self.left!r} {self.symbol} {self.right!r})"


class Unary(Expr):
    """
    An operator applied to one operand, such as `-this.n` or `~this.flags`.
    """

    __slots__ = ("op", "operand", "symbol")

    def __init__(self, op: Callable[[Any], Any], symbol: str, operand: Any):
        self.op = op
        self.symbol = symbol
        self.operand = operand

    @no_type_check
    def __call__(self, ctx: "Context") -> Any:
        value = evaluate(self.operand, ctx)
        try:
            return self.op(value)
        except Exception as error:
            raise ContextError(f"CANNOT EVALUATE {self!r}: {error!r}.") from error

    def __repr__(self) -> str:
        return f"{self.symbol}{self.operand!r}"


class Call(Expr):
    """
    A function applied to evaluated arguments, such as `lenof(this.payload)`.
    """

    __slots__ = ("args", "func")

    def __init__(self, func: Callable[..., Any], args: tuple[Any, ...]):
        self.func = func
        self.args = args

    @no_type_check
    def __call__(self, ctx: "Context") -> Any:
        args = [evaluate(arg, ctx) for arg in self.args]
        try:
            return self.func(*args)
        except Exception as error:
            raise ContextError(f"CANNOT EVALUATE {self!r}: {error!r}.") from error

    def __repr__(self) -> str:
        name = getattr(self.func, "__name__", repr(self.func))
        return f"{name}({', '.join(map(repr, self.args))})"


def lenof(value: Any) -> Expr:
    """
    The length of `value` (usually an expression), evaluated later: `lenof(this.data)`.
    """

    return Call(len, (value,))


this = This()


# No runtime type check (see `context.py`): runs for every dynamic parameter
# (counts, lengths, conditions) of every field; it accepts Any, so a check would
# catch nothing.
@no_type_check
def evaluate(value: Any, ctx: "Context") -> Any:
    """
    Return `value`, calling it with the context first if it is callable.

    Expressions and functions of the context are both callables.
    """

    if not callable(value):
        return value
    try:
        return value(ctx)
    except PaboError:
        raise
    except Exception as error:
        raise ContextError(f"CANNOT EVALUATE {value!r}: {error!r}.") from error
