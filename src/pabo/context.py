"""
Containers, contexts and references to previously parsed fields.
"""

from collections.abc import Callable
from typing import Any, no_type_check

from pabo.errors import ContextError


class Container(dict):
    """
    A dictionary whose keys can also be read and written as attributes.

    Parsed specifications are returned as containers, so `data["width"]` and
    `data.width` are the same thing. Names starting with an underscore are
    ordinary attributes and are never stored as keys.
    """

    @no_type_check
    def __getattr__(self, name: str) -> Any:
        try:
            value = self[name]
        except KeyError:
            raise AttributeError(name) from None
        return Container(value) if type(value) is dict else value

    @no_type_check
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self[name] = value

    def __delattr__(self, name: str) -> None:
        if name.startswith("_"):
            object.__delattr__(self, name)
        else:
            try:
                del self[name]
            except KeyError:
                raise AttributeError(name) from None

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict.__repr__(self)})"


class Context(Container):
    """
    The values parsed (or being built) so far, plus a link to the parent.

    Every specification creates a new context for its own fields. `ctx._` is
    the enclosing context (None at the top level), and `ctx._root` the
    outermost one. Settings such as the default endianness are attributes
    that are looked up through the parents with `setting`.
    """

    @no_type_check
    def __init__(self, data: Any = (), parent: "Context | None" = None):
        super().__init__(data)
        self.__dict__["_"] = parent

    @property
    def _root(self) -> "Context":
        ctx = self
        while ctx._ is not None:
            ctx = ctx._
        return ctx

    @no_type_check
    def setting(self, name: str, default: Any = None) -> Any:
        """
        Look up an attribute on this context or the nearest parent that has it.
        """

        ctx = self
        while ctx is not None:
            value = ctx.__dict__.get(name)
            if value is not None:
                return value
            ctx = ctx._
        return default


class This:
    """
    A reference to a field parsed earlier, such as `this.length`.

    `this.name` refers to a field of the current specification, `this._.name`
    to a field of the enclosing one, and `this._root.name` to one at the top
    level. Calling a reference with a context returns the referenced value. A
    reference is just a callable taking the context, so anything more involved
    (`this.n * 2`, say) is written as a function: `lambda ctx: ctx.n * 2`.
    In particular, `this.n == 0` compares two references and gives a plain
    bool; write `lambda ctx: ctx.n == 0` instead.
    """

    __slots__ = ("__path",)
    __path: tuple[str, ...]

    def __init__(self, path: tuple[str, ...] = ()):
        object.__setattr__(self, "_This__path", path)

    def __getattr__(self, name: str) -> "This":
        if name.startswith("__"):
            raise AttributeError(name)
        return This((*self.__path, name))

    def __getitem__(self, name: str) -> "This":
        return This((*self.__path, name))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("References are read-only.")

    @no_type_check
    def __call__(self, ctx: Context) -> Any:
        value: Any = ctx
        for name in self.__path:
            try:
                if name == "_":
                    value = value._
                elif name == "_root":
                    value = value._root
                else:
                    value = value[name]
            except (KeyError, AttributeError, TypeError):
                raise ContextError(f"Cannot resolve {self!r}.") from None
            if value is None and name in ("_", "_root"):
                raise ContextError(f"Cannot resolve {self!r}: there is no parent.")
        return value

    def __repr__(self) -> str:
        return ".".join(("this", *self.__path))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, This) and self.__path == other.__path

    def __hash__(self) -> int:
        return hash(self.__path)


this = This()

#: A value given directly, or computed from the context when parsing/building.
Dynamic = int | Callable[[Context], Any]


@no_type_check
def evaluate(value: Any, ctx: Context) -> Any:
    """
    Return `value`, calling it with the context first if it is callable.
    """

    if not callable(value):
        return value
    try:
        return value(ctx)
    except (KeyError, AttributeError) as error:
        raise ContextError(f"Cannot evaluate {value!r}: {error!r}.") from error
