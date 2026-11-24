"""
Specifications for binary data.
"""

import struct
import sys
from dataclasses import dataclass, field
from typing import no_type_check

import numpy as np

from pabo.base import Construct, Stop, hexdump, scope, tell
from pabo.bytes import Bytes, Flag
from pabo.context import Container, Context
from pabo.errors import PaboError, ValidationError
from pabo.expressions import evaluate
from pabo.hints import Endian
from pabo.numeric import ENDIANS, INT_CODES, Float, Int, _checkendian
from pabo.wrappers import Const

# numpy's codes for the struct codes a compiled plan uses (bytes are "S<n>").
NUMPY_CODES = {
    "b": "i1",
    "B": "u1",
    "h": "i2",
    "H": "u2",
    "i": "i4",
    "I": "u4",
    "q": "i8",
    "Q": "u8",
    "e": "f2",
    "f": "f4",
    "d": "f8",
    "?": "?",
}


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

    Fields whose names start with an underscore (such as `"_reserved":
    pb.Padding(4)`) are parsed and built as usual, and later fields can refer
    to them, but they are left out of the result.
    """

    fields: dict[str, Construct]
    endian: Endian | None = field(default=None, kw_only=True)
    _plans: dict = field(default_factory=dict, init=False, repr=False, compare=False)
    _entries: list = field(default_factory=list, init=False, repr=False, compare=False)
    _checks: list | None = field(default=None, init=False, repr=False, compare=False)
    _hidden: bool | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self):
        _checkendian(self.endian)

    # No runtime type check: runs for every specification parsed field by field.
    @no_type_check
    def _members(self) -> list:
        """
        The fields as (name, construct, is it `Embedded`) triples, worked out once
        (like the compiled plans) since `isinstance` on constructs is slow.
        """

        if not self._entries and self.fields:
            self._entries = [
                (name, member, isinstance(member, Embedded))
                for name, member in self.fields.items()
            ]
        return self._entries

    # No runtime type check: runs for every specification parsed or built.
    @no_type_check
    def _result(self, values: Container) -> Container:
        """
        The result to return: `values` without the fields whose names start with
        an underscore, if there are any.
        """

        if self._hidden is None:
            self._hidden = any(
                member.wraps._hashidden() if embedded else name.startswith("_")
                for name, member, embedded in self._members()
            )
        if not self._hidden:
            return values
        return Container(
            (key, value) for key, value in values.items() if not key.startswith("_")
        )

    def _hashidden(self) -> bool:
        """
        Whether any field (including embedded ones) is left out of the result.
        """

        if self._hidden is None:
            self._result(Container())
        return bool(self._hidden)

    # No runtime type check: runs for every specification parsed or built.
    @no_type_check
    def _child(self, data, parent) -> Context:
        return Context(data, parent, self.endian)

    def _size(self, ctx):
        return self._sizefields(self._child(ctx, ctx._))

    # No runtime type check: internal, called only by pabo with its own context.
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

    # No runtime type check: runs on every parse/build of a specification, and its
    # result is cached, so the check would cost more than the work.
    @no_type_check
    def _plan(self, ctx) -> "_Plan | None":
        """
        The compiled plan for the endianness in effect (this specification's, or
        that of `ctx`, the enclosing context), or None if there is none.
        """

        endian = self.endian or ctx.setting("_endian") or "little"
        if endian not in self._plans:
            self._plans[endian] = _Plan.compile(self.fields, endian)
        return self._plans[endian]

    # No runtime type check: part of the bulk fast path for `Repeat`.
    @no_type_check
    def _unpackmany(self, stream, ctx, count: int):
        """
        Unpack `count` copies in one go with the compiled plan, as the field names
        and an iterator of value tuples, or return None.
        """

        if ctx.setting("_trace") or ctx.setting("_offsets"):
            return None
        plan = self._plan(ctx)
        if plan is None or plan.consts or tell(stream) is None:
            return None
        start = stream.tell()
        raw = stream.read(plan.struct.size * count)
        if len(raw) != plan.struct.size * count:
            stream.seek(start)
            return None
        return plan.names, plan.struct.iter_unpack(raw)

    # No runtime type check: part of the bulk fast path for `Repeat`.
    @no_type_check
    def _parsemany(self, stream, ctx, count: int) -> list | None:
        """
        Parse `count` copies in one go with the compiled plan, or return None.
        """

        unpacked = self._unpackmany(stream, ctx, count)
        if unpacked is None:
            return None
        names, rows = unpacked
        if self._hashidden():
            return [self._result(Container(zip(names, values))) for values in rows]
        return [Container(zip(names, values)) for values in rows]

    # No runtime type check: part of the bulk fast path for `Repeat`.
    @no_type_check
    def _buildmany(self, data, stream, ctx) -> list | None:
        """
        Build every element of `data` with the compiled plan and write them in one
        go, or return None (having written nothing) if any of them can't be.
        """

        plan = self._plan(ctx)
        if plan is None:
            return None
        chunks, built = [], []
        names = plan.names
        hidden = self._hashidden()
        for element in data:
            packed = plan.pack(element) if isinstance(element, dict) else None
            if packed is None:
                return None
            raw, values = packed
            chunks.append(raw)
            result = Container(element)
            result.update(zip(names, values))
            built.append(self._result(result) if hidden else result)
        stream.write(b"".join(chunks))
        return built

    def _build(self, data, stream, ctx):
        if not isinstance(data, dict):
            raise PaboError(f"EXPECTED A DICT OF FIELDS, GOT {type(data).__name__}.")
        plan = self._plan(ctx)
        if plan is not None:
            packed = plan.pack(data)
            if packed is not None:
                raw, values = packed
                stream.write(raw)
                built = Container(data)
                built.update(zip(plan.names, values))
                return self._result(built)
        child = self._child(data, ctx)
        try:
            self._buildfields(stream, child)
        except Stop:
            pass
        return self._result(Container(child))

    # No runtime type check: the per-field loop of every build; internal only.
    @no_type_check
    def _buildfields(self, stream, child: Context) -> None:
        for name, member, embedded in self._members():
            if embedded:
                member.wraps._buildfields(stream, child)
                continue
            with scope(name, stream, member.docs):
                if name in child:
                    value = child[name]
                elif member._omittable():
                    value = None
                else:
                    raise PaboError(
                        f"MISSING FIELD {name!r}. DATA NOT ACCORDING TO SPECIFICATION."
                    )
                child[name] = member._build(value, stream, child)

    def _parse(self, stream, ctx):
        if not ctx.setting("_trace") and not ctx.setting("_offsets"):
            plan = self._plan(ctx)
            if plan is not None:
                values = plan.unpack(stream)
                if values is not None:
                    return self._result(Container(zip(plan.names, values)))
        child = self._child((), ctx)
        try:
            self._parsefields(stream, child)
        except Stop:
            pass
        if self._checks is None or self._checks:
            self._checkrebuilds(stream, child)
        result = self._result(Container(child))
        if child.setting("_offsets"):
            positions = child.__dict__.get("_positions", {})
            result._offsets = {
                name: span for name, span in positions.items() if name in result
            }
        return result

    def _checkrebuilds(self, stream, child: Context) -> None:
        """
        Compare the fields that are `Rebuild(..., check=True)` with what they
        would be built as, now that every field has been parsed.
        """

        if self._checks is None:
            self._checks = [
                (name, member, embedded)
                for name, member, embedded in self._members()
                if embedded or getattr(member, "check", False) is True
            ]
        for name, member, embedded in self._checks:
            if embedded:
                member.wraps._checkrebuilds(stream, child)
            elif name in child:
                with scope(name, stream, member.docs):
                    expected = evaluate(member.func, child)
                    if _differs(child[name], expected):
                        raise ValidationError(
                            f"THE VALUE {child[name]!r} DOES NOT MATCH THE "
                            f"{expected!r} IT WOULD BE BUILT AS."
                        )

    # No runtime type check: the per-field loop of every parse; internal only.
    @no_type_check
    def _parsefields(self, stream, child: Context) -> None:
        trace = child.setting("_trace")
        record = child.setting("_offsets")
        if record:
            positions = child.__dict__.setdefault("_positions", {})
        for name, member, embedded in self._members():
            if embedded:
                member.wraps._parsefields(stream, child)
                continue
            start = tell(stream) if trace or record else None
            with scope(name, stream, member.docs):
                child[name] = member._parse(stream, child)
            if record:
                positions[name] = (start, tell(stream))
            if trace:
                _tracefield(trace, stream, child, name, start, child[name])

    def _numpydtype(self, ctx) -> "np.dtype | None":
        """
        The numpy structured dtype of one record (for `Array`), or None if the
        fields can't be compiled into one.
        """

        plan = self._plan(ctx)
        return None if plan is None else plan.numpydtype()

    def _constants(self) -> dict:
        """
        The constant fields and their values (for `Array`).
        """

        return {
            name: member.value
            for name, member in self.fields.items()
            if isinstance(member, Const)
        }

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


@dataclass
class Focused(Construct):
    """
    One field of a specification: the whole specification is parsed, and the
    value of the field `name` returned (such as the payload after a header).

    When building, the given value is that field's, so the other fields must
    be ones that build without a value (constants, padding, `Rebuild`, ...).
    """

    wraps: Specification
    name: str

    def __post_init__(self):
        if self.name not in self.wraps.fields or self.name.startswith("_"):
            raise PaboError(
                f"{self.name!r} IS NOT A FIELD OF THE SPECIFICATION (OR IS HIDDEN)."
            )

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        self.wraps._build({self.name: data}, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        return self.wraps._parse(stream, ctx)[self.name]


def _differs(a, b) -> bool:
    """
    Whether two values differ (also for numpy arrays, whose `!=` is elementwise).
    """

    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return not np.array_equal(a, b)
    return a != b


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
        self.flags = "?" in layout
        self._numpy = None
        # The positions of the constants among the values, and their values.
        self.checks = [
            (ix, consts[name]) for ix, name in enumerate(names) if name in consts
        ]

    @classmethod
    def compile(cls, fields: dict, endian: Endian) -> "_Plan | None":
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

    def numpydtype(self) -> np.dtype:
        """
        The numpy structured dtype with the same layout, made once.
        """

        if self._numpy is None:
            order = self.struct.format[0]
            self._numpy = np.dtype(
                [
                    (
                        name,
                        f"S{code[:-1]}"
                        if code.endswith("s")
                        else order + NUMPY_CODES[code],
                    )
                    for name, code in zip(self.names, self.layout)
                ]
            )
        return self._numpy

    # No runtime type check: the compiled fast path, which exists only for speed.
    @no_type_check
    def unpack(self, stream) -> tuple | None:
        """
        Read the values of every field, in order, or return None having moved
        nothing.
        """

        try:
            start = stream.tell()
        except (AttributeError, OSError, ValueError):
            return None  # the stream cannot rewind, so parse field by field
        raw = stream.read(self.struct.size)
        if len(raw) != self.struct.size:
            stream.seek(start)
            return None
        values = self.struct.unpack(raw)
        for ix, value in self.checks:
            if values[ix] != value:
                stream.seek(start)
                return None
        return values

    # No runtime type check: the compiled fast path, which exists only for speed.
    @no_type_check
    def pack(self, data) -> tuple[bytes, list] | None:
        """
        The bytes for the field values in `data` (a dict), and the values written
        (with constants filled in and flags as bools), or None.
        """

        values = []
        consts, lengths = self.consts, self.lengths
        for name in self.names:
            value = data.get(name)
            if value is not None:
                if name in consts and value != consts[name]:
                    return None
            elif name in consts:
                value = consts[name]
            else:
                return None
            if name in lengths and (
                not isinstance(value, (bytes, bytearray)) or len(value) != lengths[name]
            ):
                return None
            values.append(value)
        try:
            raw = self.struct.pack(*values)
        except struct.error:
            return None
        if self.flags:
            values = [
                bool(value) if code == "?" else value
                for code, value in zip(self.layout, values)
            ]
        return raw, values
