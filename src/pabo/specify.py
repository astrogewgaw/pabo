"""
Specifications for binary data.
"""

from dataclasses import dataclass, field

from pabo.base import Construct, Stop, scope
from pabo.context import Container, Context
from pabo.errors import PaboError
from pabo.numeric import Endian, _check_endian


@dataclass
class Specification(Construct[Container]):
    """
    Represents a specification for binary data: an ordered set of named fields.

    Parsing returns a `Container` (a dict whose keys are also attributes).
    Each field can refer to the fields before it, through `this.name` or a
    function of the context. When building, the whole input is visible to
    every field, so a field can also be computed from the ones after it.

    `endian` sets the default endianness of the numbers inside (including
    nested specifications) that don't give their own.
    """

    fields: dict[str, Construct]
    endian: Endian | None = field(default=None, kw_only=True)

    def __post_init__(self):
        _check_endian(self.endian)

    def _child(self, data, parent) -> Context:
        child = Context(data, parent=parent)
        child._endian = self.endian
        return child

    def _size(self, ctx):
        return self._size_fields(self._child(ctx, ctx._))

    def _size_fields(self, child: Context) -> int:
        total = 0
        for name, field in self.fields.items():
            if isinstance(field, Embedded):
                total += field.wraps._size_fields(child)
                continue
            value = child.get(name)
            sub = Context(value, parent=child) if isinstance(value, dict) else child
            total += field._size(sub)
        return total

    def _build(self, data, stream, ctx):
        if not isinstance(data, dict):
            raise PaboError(f"Expected a dict of fields, got {type(data).__name__}.")
        child = self._child(data, ctx)
        try:
            self._build_fields(stream, child)
        except Stop:
            pass
        return Container(child)

    def _build_fields(self, stream, child: Context) -> None:
        for name, field in self.fields.items():
            if isinstance(field, Embedded):
                field.wraps._build_fields(stream, child)
                continue
            with scope(name, stream, field.docs):
                if name in child:
                    value = child[name]
                elif field._omittable():
                    value = None
                else:
                    raise PaboError(
                        f"Missing field {name!r}. Data not according to specification."
                    )
                child[name] = field._build(value, stream, child)

    def _parse(self, stream, ctx):
        child = self._child((), ctx)
        try:
            self._parse_fields(stream, child)
        except Stop:
            pass
        return Container(child)

    def _parse_fields(self, stream, child: Context) -> None:
        for name, field in self.fields.items():
            if isinstance(field, Embedded):
                field.wraps._parse_fields(stream, child)
                continue
            with scope(name, stream, field.docs):
                child[name] = field._parse(stream, child)


@dataclass
class Embedded(Construct[Container]):
    """
    Put the fields of a specification directly into the enclosing one.

    The key it is stored under in the enclosing specification is ignored, and
    the embedded fields share the enclosing context (and its endianness).
    On its own, it behaves like the specification it wraps.
    """

    wraps: Specification

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        return self.wraps._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        return self.wraps._parse(stream, ctx)
