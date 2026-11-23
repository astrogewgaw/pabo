"""
Specifications for binary data.
"""

import struct
import sys
from dataclasses import dataclass, field
from typing import no_type_check

from pabo.base import Construct, Stop, hexdump, scope, tell
from pabo.bytes import Bytes, Flag
from pabo.context import Container, Context
from pabo.errors import PaboError
from pabo.numeric import ENDIANS, INT_CODES, Endian, Float, Int, _checkendian
from pabo.wrappers import Const


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
    _plans: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self):
        _checkendian(self.endian)

    @no_type_check
    def _child(self, data, parent) -> Context:
        child = Context(data, parent=parent)
        child.__dict__["_endian"] = self.endian
        return child

    def _size(self, ctx):
        return self._sizefields(self._child(ctx, ctx._))

    @no_type_check
    def _sizefields(self, child: Context) -> int:
        total = 0
        for name, member in self.fields.items():
            if isinstance(member, Embedded):
                total += member.wraps._sizefields(child)
                continue
            value = child.get(name)
            sub = Context(value, parent=child) if isinstance(value, dict) else child
            total += member._size(sub)
        return total

    @no_type_check
    def _plan(self, ctx) -> "_Plan | None":
        """
        The compiled plan for the endianness in effect, or None if there is none.
        """

        endian = self.endian or ctx.setting("_endian") or "little"
        if endian not in self._plans:
            self._plans[endian] = _Plan.compile(self.fields, endian)
        return self._plans[endian]

    @no_type_check
    def _parsemany(self, stream, ctx, count: int) -> list | None:
        """
        Parse `count` copies in one go with the compiled plan, or return None.
        """

        if ctx.setting("_trace"):
            return None
        plan = self._plan(self._child((), ctx))
        if plan is None or plan.consts or tell(stream) is None:
            return None
        start = stream.tell()
        raw = stream.read(plan.struct.size * count)
        if len(raw) != plan.struct.size * count:
            stream.seek(start)
            return None
        names = plan.names
        return [
            Container(zip(names, values)) for values in plan.struct.iter_unpack(raw)
        ]

    def _build(self, data, stream, ctx):
        if not isinstance(data, dict):
            raise PaboError(f"Expected a dict of fields, got {type(data).__name__}.")
        child = self._child(data, ctx)
        plan = self._plan(child)
        if plan is not None:
            raw = plan.pack(child)
            if raw is not None:
                stream.write(raw)
                return Container(child)
        try:
            self._buildfields(stream, child)
        except Stop:
            pass
        return Container(child)

    @no_type_check
    def _buildfields(self, stream, child: Context) -> None:
        for name, member in self.fields.items():
            if isinstance(member, Embedded):
                member.wraps._buildfields(stream, child)
                continue
            with scope(name, stream, member.docs):
                if name in child:
                    value = child[name]
                elif member._omittable():
                    value = None
                else:
                    raise PaboError(
                        f"Missing field {name!r}. Data not according to specification."
                    )
                child[name] = member._build(value, stream, child)

    def _parse(self, stream, ctx):
        child = self._child((), ctx)
        if not child.setting("_trace"):
            plan = self._plan(child)
            if (
                plan is not None
                and tell(stream) is not None
                and plan.unpack(stream, child)
            ):
                return Container(child)
        try:
            self._parsefields(stream, child)
        except Stop:
            pass
        return Container(child)

    @no_type_check
    def _parsefields(self, stream, child: Context) -> None:
        trace = child.setting("_trace")
        for name, member in self.fields.items():
            if isinstance(member, Embedded):
                member.wraps._parsefields(stream, child)
                continue
            start = tell(stream) if trace else None
            with scope(name, stream, member.docs):
                child[name] = member._parse(stream, child)
            if trace:
                _tracefield(trace, stream, child, name, start, child[name])

    def _label(self) -> str:
        return "Specification" + (f"(endian={self.endian!r})" if self.endian else "")

    def _rows(self, name, depth, offset):
        rows = list(self._fieldrows(depth + (1 if name else 0), offset))
        try:
            size = self.size
        except PaboError:
            size = None
        if name:
            yield offset, size, name, depth, self._label(), self.docs
        yield from rows

    def _fieldrows(self, depth, offset):
        for name, member in self.fields.items():
            if isinstance(member, Embedded):
                rows = list(member.wraps._fieldrows(depth, offset))
            else:
                rows = list(member._rows(name, depth, offset))
            yield from rows
            top = [row for row in rows if row[3] == depth]
            sizes = [row[1] for row in top]
            if offset is None or any(size is None for size in sizes):
                offset = None
            else:
                offset += sum(size or 0 for size in sizes)


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


def _tracefield(
    trace, stream, ctx: Context, name: str, start: int | None, value
) -> None:
    """
    Print a parsed member, with the bytes it came from, for `parse(..., trace=True)`.
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


class _Plan:
    """
    A specification of fixed-size numbers, bytes and constants, compiled into a
    single `struct.Struct`, so it can be parsed and built in one call.

    `unpack`/`pack` return a false value when anything goes wrong; the caller
    then rewinds and takes the field-by-field path, which raises the detailed
    error.
    """

    def __init__(self, names, layout, struct_, consts, lengths):
        self.names = names
        self.layout = layout
        self.struct = struct_
        self.consts = consts
        self.lengths = lengths

    @classmethod
    def compile(cls, fields: dict, endian: str) -> "_Plan | None":
        codes, names, consts, lengths = [], [], {}, {}
        for name, construct in fields.items():
            if isinstance(construct, Const):
                consts[name] = construct.value
                construct = construct.wraps
            if type(construct) is Int and construct.width in INT_CODES:
                if (construct.endian or endian) != endian:
                    return None
                code = INT_CODES[construct.width]
                codes.append(code if construct.signed else code.upper())
            elif type(construct) is Float:
                if (construct.endian or endian) != endian:
                    return None
                codes.append(construct.formatfor(endian)[1:])
            elif (
                type(construct) is Bytes
                and isinstance(construct.count, int)
                and construct.count >= 0
            ):
                codes.append(f"{construct.count}s")
                lengths[name] = construct.count
            elif type(construct) is Flag:
                codes.append("?")
            else:
                return None
            names.append(name)
        if not names:
            return None
        return cls(
            names,
            codes,
            struct.Struct(ENDIANS[endian] + "".join(codes)),
            consts,
            lengths,
        )

    @no_type_check
    def unpack(self, stream, ctx: Context) -> bool:
        start = stream.tell()
        raw = stream.read(self.struct.size)
        if len(raw) != self.struct.size:
            stream.seek(start)
            return False
        values = self.struct.unpack(raw)
        for name, value in zip(self.names, values):
            if name in self.consts and value != self.consts[name]:
                stream.seek(start)
                return False
        ctx.update(zip(self.names, values))
        return True

    @no_type_check
    def pack(self, ctx: Context) -> bytes | None:
        values = []
        for name in self.names:
            if name in ctx and ctx[name] is not None:
                value = ctx[name]
                if name in self.consts and value != self.consts[name]:
                    return None
            elif name in self.consts:
                value = self.consts[name]
            else:
                return None
            if name in self.lengths and (
                not isinstance(value, (bytes, bytearray))
                or len(value) != self.lengths[name]
            ):
                return None
            values.append(value)
        try:
            raw = self.struct.pack(*values)
        except struct.error:
            return None
        for name, code, value in zip(self.names, self.layout, values):
            ctx[name] = bool(value) if code == "?" else value
        return raw
