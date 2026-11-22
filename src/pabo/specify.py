"""
Specifications for binary data.
"""

from dataclasses import dataclass, field

import sys

from pabo.base import Construct, Stop, hexdump, scope, tell
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
        trace = child.setting("_trace")
        for name, field in self.fields.items():
            if isinstance(field, Embedded):
                field.wraps._parse_fields(stream, child)
                continue
            start = tell(stream) if trace else None
            with scope(name, stream, field.docs):
                child[name] = field._parse(stream, child)
            if trace:
                _trace_field(trace, stream, child, name, start, child[name])

    def _label(self) -> str:
        return "Specification" + (f"(endian={self.endian!r})" if self.endian else "")

    def _rows(self, name, depth, offset):
        rows = list(self._field_rows(depth + (1 if name else 0), offset))
        try:
            size = self.size
        except PaboError:
            size = None
        if name:
            yield offset, size, name, depth, self._label(), self.docs
        yield from rows

    def _field_rows(self, depth, offset):
        for name, field in self.fields.items():
            if isinstance(field, Embedded):
                rows = list(field.wraps._field_rows(depth, offset))
            else:
                rows = list(field._rows(name, depth, offset))
            yield from rows
            top = [row for row in rows if row[3] == depth]
            sizes = [row[1] for row in top]
            if offset is None or any(size is None for size in sizes):
                offset = None
            else:
                offset += sum(sizes)


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


def _trace_field(trace, stream, ctx: Context, name: str, start: int | None, value) -> None:
    """
    Print a parsed field, with the bytes it came from, for `parse(..., trace=True)`.
    """

    file = trace if hasattr(trace, "write") else sys.stderr
    depth, parent = 0, ctx._
    while parent is not None:
        depth, parent = depth + 1, parent._
    end = tell(stream)
    raw = b""
    if start is not None and end is not None:
        stream.seek(start)
        raw = stream.read(end - start)
        stream.seek(end)
    where = f"[{start}:{end}]" if start is not None else ""
    indent = "  " * max(depth - 1, 0)
    shown = repr(value)
    if len(shown) > 60:
        shown = shown[:57] + "..."
    print(f"{indent}{name} {where} = {shown}", file=file)
    for line in hexdump(raw[:64], start or 0).splitlines():
        print(f"{indent}    {line}", file=file)
