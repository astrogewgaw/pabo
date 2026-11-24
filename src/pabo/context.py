"""
Containers and contexts: the values parsed (or being built) so far.

References to them (`this.length`, ...) live in `expressions.py`.

pabo checks type hints at runtime with beartype (see `pabo/__init__.py`). A few
internal functions here, in `expressions.py` and in `specify.py` are marked
`@no_type_check`, which
tells beartype to skip them: they run once per field (or per attribute access)
during every parse, only ever receive arguments pabo itself created, and
checking them made parsing about twice as slow (a PNG header went from about
2 µs to about 5 µs). Public functions, and the constructors of every construct,
are still checked.
"""

from typing import Any, no_type_check


class Container(dict):
    """
    A dictionary whose keys can also be read and written as attributes.

    Parsed specifications are returned as containers, so `data["width"]` and
    `data.width` are the same thing. Names starting with an underscore are
    ordinary attributes and are never stored as keys.
    """

    # No runtime type check (see the module docstring): runs on every attribute
    # read of a parsed result or context, e.g. each `ctx.n` in a lambda.
    @no_type_check
    def __getattr__(self, name: str) -> Any:
        try:
            value = self[name]
        except KeyError:
            raise AttributeError(name) from None
        return Container(value) if type(value) is dict else value

    # No runtime type check: runs on every attribute write, including the
    # settings each specification stores on its context.
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
    outermost one. `ctx._params` holds the parameters given to `parse` or
    `build` (None if there are none). They and the settings `_endian` (the default endianness, which
    `endian` overrides) and `_trace` are attributes, copied from the parent
    when the context is created; settings are read with `setting`.
    """

    # No runtime type check: a context is created for every specification parsed,
    # and the forward reference in the hint is slow for beartype to resolve.
    @no_type_check
    def __init__(
        self, data: Any = (), parent: "Context | None" = None, endian: Any = None
    ):
        dict.__init__(self, data)
        attrs = self.__dict__
        attrs["_"] = parent
        if parent is None:
            attrs["_endian"] = endian
            attrs["_trace"] = None
            attrs["_params"] = None
        else:
            inherited = parent.__dict__
            attrs["_endian"] = endian or inherited.get("_endian")
            attrs["_trace"] = inherited.get("_trace")
            attrs["_params"] = inherited.get("_params")

    @property
    def _root(self) -> "Context":
        ctx = self
        while ctx._ is not None:
            ctx = ctx._
        return ctx

    # No runtime type check: called for every specification parsed (endianness,
    # tracing), and it only reads attributes pabo itself set.
    @no_type_check
    def setting(self, name: str, default: Any = None) -> Any:
        """
        The value of a setting such as `_endian`, or `default` if it is not set.
        """

        value = self.__dict__.get(name)
        return default if value is None else value
