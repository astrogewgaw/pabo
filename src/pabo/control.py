"""
Control flow: computed, conditional, switched and validated fields.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pabo.base import Construct, Stop, scope, tell
from pabo.context import evaluate
from pabo.errors import PaboError, SizeofError, StreamError, ValidationError


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
    """

    wraps: Construct
    func: Callable

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

    cond: Any
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
            raise ValidationError("A value is required, since the condition holds.")
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
        raise SizeofError("An Optional construct has no fixed size.")

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

    key: Any
    cases: dict[Any, Construct]
    default: Construct | None = None

    def _case(self, ctx) -> Construct:
        key = evaluate(self.key, ctx)
        case = self.cases.get(key, self.default)
        if case is None:
            raise ValidationError(f"No case for the key {key!r}.")
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
    elements are `Container`s, with attribute access).
    """

    predicate: Callable
    wraps: Construct

    def _size(self, ctx):
        raise SizeofError("A RepeatUntil construct has no fixed size.")

    def _build(self, data, stream, ctx):
        built = []
        for ix, element in enumerate(data):
            with scope(f"[{ix}]", stream):
                value = self.wraps._build(element, stream, ctx)
            built.append(value)
            if self.predicate(value, ctx):
                return built
        raise ValidationError(
            "No element satisfies the predicate, so nothing ends the list."
        )

    def _parse(self, stream, ctx):
        data = []
        while True:
            with scope(f"[{len(data)}]", stream):
                element = self.wraps._parse(stream, ctx)
            data.append(element)
            if self.predicate(element, ctx):
                return data


@dataclass
class StopIf(Construct):
    """
    Stop parsing/building the enclosing specification or sequence if `cond` holds.

    The fields after it are left out of the result.
    """

    cond: Any

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
                f"Expected the end of the stream, at offset {tell(stream)}."
            )
        return None


@dataclass
class Check(Construct):
    """
    Check that `func(ctx)` holds, when parsing and when building. Takes no bytes.
    """

    func: Callable
    message: str = field(default="Check failed.", kw_only=True)

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
    predicate: Callable
    message: str = field(default="", kw_only=True)

    def _omittable(self):
        return self.wraps._omittable()

    def _check(self, value, ctx):
        if not self.predicate(value, ctx):
            raise ValidationError(self.message or f"The value {value!r} is not valid.")
        return value

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        self._check(data, ctx)
        return self.wraps._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        return self._check(self.wraps._parse(stream, ctx), ctx)
