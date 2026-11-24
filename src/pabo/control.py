"""
Control flow: computed, conditional, switched and validated fields.
"""

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

from pabo.base import Construct, Stop, scope, tell
from pabo.context import Container, Context
from pabo.errors import (
    PaboError,
    SizeofError,
    StreamError,
    ValidationError,
    attempt,
)
from pabo.expressions import evaluate
from pabo.hints import Condition, ContextFunction, Key, Predicate


@dataclass
class Computed(Construct):
    """
    A value computed from the context, which takes up no bytes.

    `func` is a value or a function of the context. Any value given when
    building is ignored, and the computed one is used instead.
    """

    func: Any

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _build(self, data, stream, ctx):
        return evaluate(self.func, ctx)

    def _parse(self, stream, ctx):
        return evaluate(self.func, ctx)


@dataclass
class Rebuild(Construct):
    """
    A field whose value is computed from the context when building.

    Parsing reads the value as usual. Building ignores any given value and
    writes `func(ctx)` instead, for example a length prefix computed from the
    payload after it: `Rebuild(Int(2), lambda ctx: len(ctx.payload))`.

    With `check=True`, the value read is also compared with `func(ctx)` once
    the enclosing specification has parsed all its fields (so `func` can use
    the fields after it), and a mismatch raises a `ValidationError`.
    """

    wraps: Construct
    func: ContextFunction
    check: bool = False

    def _omittable(self):
        return True

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        return self.wraps._build(evaluate(self.func, ctx), stream, ctx)

    def _parse(self, stream, ctx):
        return self.wraps._parse(stream, ctx)


@dataclass
class If(Construct):
    """
    Parse/build `then` if `cond` holds, else `otherwise` (or nothing, giving None).

    `cond` is a value or a function of the context.
    """

    cond: Condition
    then: Construct
    otherwise: Construct | None = None

    def _branch(self, ctx) -> Construct | None:
        return self.then if evaluate(self.cond, ctx) else self.otherwise

    def _omittable(self):
        if self.otherwise is None:
            return True
        return self.then._omittable() and self.otherwise._omittable()

    def _size(self, ctx):
        branch = self._branch(ctx)
        return 0 if branch is None else branch._size(ctx)

    def _build(self, data, stream, ctx):
        branch = self._branch(ctx)
        if branch is None:
            return None
        if data is None and not branch._omittable():
            raise ValidationError("A VALUE IS REQUIRED, SINCE THE CONDITION HOLDS.")
        return branch._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        branch = self._branch(ctx)
        return None if branch is None else branch._parse(stream, ctx)


@dataclass
class Optional(Construct):
    """
    Parse `wraps` if possible, else rewind and return None.

    Building None writes nothing.
    """

    wraps: Construct

    def _omittable(self):
        return True

    def _size(self, ctx):
        raise SizeofError("AN OPTIONAL CONSTRUCT HAS NO FIXED SIZE.")

    def _build(self, data, stream, ctx):
        if data is None:
            return None
        return self.wraps._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        start = stream.tell()
        try:
            return self.wraps._parse(stream, ctx)
        except PaboError:
            stream.seek(start)
            return None


@dataclass
class Switch(Construct):
    """
    Choose a construct from `cases` by the value of `key` (a tagged union).

    `key` is a value or a function of the context, usually `this.tag`. If no
    case matches, `default` is used, or a `ValidationError` is raised.
    """

    key: Key
    cases: dict[Any, Construct]
    default: Construct | None = None

    def _case(self, ctx) -> Construct:
        key = evaluate(self.key, ctx)
        case = self.cases.get(key, self.default)
        if case is None:
            raise ValidationError(f"NO CASE FOR THE KEY {key!r}.")
        return case

    def _size(self, ctx):
        return self._case(ctx)._size(ctx)

    def _build(self, data, stream, ctx):
        return self._case(ctx)._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        return self._case(ctx)._parse(stream, ctx)


@dataclass
class RepeatUntil(Construct[list]):
    """
    Repeat `wraps` until `predicate(element, ctx)` holds for an element.

    The element that satisfies the predicate is included in the result. When
    building, the predicate sees each element as built (so a specification's
    elements are `Container` objects, with attribute access).
    """

    predicate: Predicate
    wraps: Construct

    def _size(self, ctx):
        raise SizeofError("A RepeatUntil CONSTRUCT HAS NO FIXED SIZE.")

    def _build(self, data, stream, ctx):
        built = []
        attrs, previous = ctx.__dict__, ctx.__dict__.get("_index")
        try:
            for ix, element in enumerate(data):
                attrs["_index"] = ix
                with scope(f"[{ix}]", stream):
                    value = self.wraps._build(element, stream, ctx)
                built.append(value)
                if attempt(self.predicate, value, ctx):
                    return built
        finally:
            attrs["_index"] = previous
        raise ValidationError(
            "NO ELEMENT SATISFIES THE PREDICATE, SO NOTHING ENDS THE LIST."
        )

    def _parse(self, stream, ctx):
        data = []
        attrs, previous = ctx.__dict__, ctx.__dict__.get("_index")
        try:
            while True:
                attrs["_index"] = len(data)
                with scope(f"[{len(data)}]", stream):
                    element = self.wraps._parse(stream, ctx)
                data.append(element)
                if attempt(self.predicate, element, ctx):
                    return data
        finally:
            attrs["_index"] = previous


@dataclass
class StopIf(Construct):
    """
    Stop parsing/building the enclosing specification or sequence if `cond` holds.

    The fields after it are left out of the result.
    """

    cond: Condition

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _build(self, data, stream, ctx):
        if evaluate(self.cond, ctx):
            raise Stop
        return None

    def _parse(self, stream, ctx):
        if evaluate(self.cond, ctx):
            raise Stop
        return None


@dataclass
class Terminated(Construct):
    """
    Check that the stream has ended. Builds nothing.
    """

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _build(self, data, stream, ctx):
        return None

    def _parse(self, stream, ctx):
        if stream.read(1):
            raise StreamError(
                f"EXPECTED THE END OF THE STREAM, AT OFFSET {tell(stream)}."
            )
        return None


@dataclass
class Check(Construct):
    """
    Check that `func(ctx)` holds, when parsing and when building. Takes no bytes.
    """

    func: ContextFunction
    message: str = field(default="CHECK FAILED.", kw_only=True)

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _check(self, ctx):
        if not evaluate(self.func, ctx):
            raise ValidationError(self.message)

    def _build(self, data, stream, ctx):
        self._check(ctx)
        return None

    def _parse(self, stream, ctx):
        self._check(ctx)
        return None


@dataclass
class Validated(Construct):
    """
    Check every value parsed or built by `wraps` with `predicate(value, ctx)`.
    """

    wraps: Construct
    predicate: Predicate
    message: str = field(default="", kw_only=True)

    def _omittable(self):
        return self.wraps._omittable()

    def _check(self, value, ctx):
        if not attempt(self.predicate, value, ctx):
            raise ValidationError(self.message or f"THE VALUE {value!r} IS NOT VALID.")
        return value

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        self._check(data, ctx)
        return self.wraps._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        return self._check(self.wraps._parse(stream, ctx), ctx)


@dataclass
class Union(Construct[Container]):
    """
    Several views of the same bytes: every field is parsed from the same start.

    Parsing gives a `Container` with every field, and moves past the longest
    of them. Building writes the first field that is given (not None), padded
    with null bytes to the size of the largest field when the sizes are fixed.
    Fields can refer to the fields before them, as in a specification.
    """

    fields: dict[str, Construct]

    def __post_init__(self):
        if not self.fields:
            raise PaboError("A UNION NEEDS AT LEAST ONE FIELD.")

    def _size(self, ctx):
        return max(member._size(ctx) for member in self.fields.values())

    def _build(self, data, stream, ctx):
        if not isinstance(data, dict):
            raise PaboError(f"EXPECTED A DICT OF FIELDS, GOT {type(data).__name__}.")
        given = [name for name in self.fields if data.get(name) is not None]
        if not given:
            raise ValidationError(
                f"NONE OF THE FIELDS OF THE UNION WAS GIVEN: {list(self.fields)}."
            )
        name = given[0]
        member = self.fields[name]
        buffer = BytesIO()
        with scope(name, stream, member.docs):
            built = member._build(data[name], buffer, Context(data, ctx))
        raw = buffer.getvalue()
        try:
            size = self._size(Context(data, ctx))
        except PaboError:
            size = len(raw)
        stream.write(raw + b"\x00" * (size - len(raw)))
        return Container({name: built})

    def _parse(self, stream, ctx):
        start = stream.tell()
        end = start
        child = Context((), ctx)
        for name, member in self.fields.items():
            stream.seek(start)
            with scope(name, stream, member.docs):
                child[name] = member._parse(stream, child)
            end = max(end, stream.tell())
        stream.seek(end)
        return Container(child)


@dataclass
class Select(Construct):
    """
    The first of several alternatives that parses (or builds) without an error.

    Each alternative that fails is undone (the stream is rewound) before the
    next is tried. If none works, the error says why each one failed.
    """

    alternatives: list[Construct]

    def __post_init__(self):
        if not self.alternatives:
            raise PaboError("A Select NEEDS AT LEAST ONE ALTERNATIVE.")

    def _size(self, ctx):
        sizes = {alternative._size(ctx) for alternative in self.alternatives}
        if len(sizes) != 1:
            raise SizeofError("THE ALTERNATIVES OF THIS Select DIFFER IN SIZE.")
        return sizes.pop()

    def _fail(self, errors: list) -> ValidationError:
        reasons = "; ".join(f"{ix}: {error.msg}" for ix, error in errors)
        return ValidationError(f"NO ALTERNATIVE WORKED ({reasons})")

    def _build(self, data, stream, ctx):
        errors = []
        for ix, alternative in enumerate(self.alternatives):
            buffer = BytesIO()
            try:
                built = alternative._build(data, buffer, ctx)
            except PaboError as error:
                errors.append((ix, error))
                continue
            stream.write(buffer.getvalue())
            return built
        raise self._fail(errors)

    def _parse(self, stream, ctx):
        start = stream.tell()
        errors = []
        for ix, alternative in enumerate(self.alternatives):
            stream.seek(start)
            try:
                return alternative._parse(stream, ctx)
            except PaboError as error:
                errors.append((ix, error))
        stream.seek(start)
        raise self._fail(errors)


@dataclass
class Deferred(Construct):
    """
    The construct returned by `func(ctx)`, chosen each time it is parsed or built.

    Use it when a layout is only known from data parsed earlier (such as the
    columns of a table described by its header), or for recursive layouts,
    where a construct contains itself:

        node = pb.Spec({
            "value": pb.u8,
            "count": pb.Rebuild(pb.u8, pb.lenof(this.children)),
            "children": pb.Repeat(pb.Deferred(lambda ctx: node), this.count),
        })
    """

    func: ContextFunction

    def _choose(self, ctx) -> Construct:
        chosen = evaluate(self.func, ctx)
        if not isinstance(chosen, Construct):
            raise ValidationError(
                f"THE FUNCTION OF A Deferred MUST RETURN A CONSTRUCT, GOT {chosen!r}."
            )
        return chosen

    def _omittable(self):
        return False

    def _size(self, ctx):
        return self._choose(ctx)._size(ctx)

    def _build(self, data, stream, ctx):
        return self._choose(ctx)._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        return self._choose(ctx)._parse(stream, ctx)
