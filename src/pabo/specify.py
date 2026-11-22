"""
Specifications for binary data.
"""

from dataclasses import dataclass

from pabo.base import Construct, scope
from pabo.context import Container, Context
from pabo.errors import PaboError


@dataclass
class Specification(Construct[Container]):
    """
    Represents a specification for binary data: an ordered set of named fields.

    Parsing returns a `Container` (a dict whose keys are also attributes).
    Each field can refer to the fields before it, through `this.name` or a
    function of the context. When building, the whole input is visible to
    every field, so a field can also be computed from the ones after it.
    """

    fields: dict[str, Construct]

    def _size(self, ctx):
        child = Context(ctx, parent=ctx._)
        total = 0
        for name, field in self.fields.items():
            value = child.get(name)
            sub = Context(value, parent=child) if isinstance(value, dict) else child
            total += field._size(sub)
        return total

    def _build(self, data, stream, ctx):
        if not isinstance(data, dict):
            raise PaboError(f"Expected a dict of fields, got {type(data).__name__}.")
        child = Context(data, parent=ctx)
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
        return Container(child)

    def _parse(self, stream, ctx):
        child = Context(parent=ctx)
        for name, field in self.fields.items():
            with scope(name, stream):
                child[name] = field._parse(stream, child)
        return Container(child)
