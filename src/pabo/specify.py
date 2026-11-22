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
        child = self._child(ctx, ctx._)
        total = 0
        for name, field in self.fields.items():
            value = child.get(name)
            sub = Context(value, parent=child) if isinstance(value, dict) else child
            total += field._size(sub)
        return total

    def _build(self, data, stream, ctx):
        if not isinstance(data, dict):
            raise PaboError(f"Expected a dict of fields, got {type(data).__name__}.")
        child = self._child(data, ctx)
        try:
            for name, field in self.fields.items():
                with scope(name, stream):
                    if name in child:
                        value = child[name]
                    elif field._omittable():
                        value = None
                    else:
                        raise PaboError(
                            f"Missing field {name!r}. Data not according to specification."
                        )
                    child[name] = field._build(value, stream, child)
        except Stop:
            pass
        return Container(child)

    def _parse(self, stream, ctx):
        child = self._child((), ctx)
        try:
            for name, field in self.fields.items():
                with scope(name, stream):
                    child[name] = field._parse(stream, child)
        except Stop:
            pass
        return Container(child)
