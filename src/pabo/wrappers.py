"""
Wrappers for constructs.
"""

from collections.abc import Callable, MutableSequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

from pabo.base import Construct, Stop, read_exactly, scope
from pabo.context import Dynamic, evaluate
from pabo.errors import ConstError, PaboError, SizeofError, ValidationError
from pabo.numeric import Int


def _int(value, ctx, what: str = "count") -> int:
    value = evaluate(value, ctx)
    if not isinstance(value, int):
        raise PaboError(f"The {what} must be an integer, got {value!r}.")
    return value


@dataclass
class Const(Construct):
    """
    Represents a binary construct that is constant.

    When building, the value may be omitted (None); it is filled in automatically.
    """

    value: Any
    wraps: Construct

    def _omittable(self):
        return True

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        if data is not None and data != self.value:
            raise ConstError(f"Cannot build {data!r}: the constant is {self.value!r}.")
        self.wraps._build(self.value, stream, ctx)
        return self.value

    def _parse(self, stream, ctx):
        data = self.wraps._parse(stream, ctx)
        if data != self.value:
            raise ConstError(
                f"Parsed {data!r}, but expected the constant {self.value!r}."
            )
        return data

    def build(self, data=None, src=None, append: bool = False) -> bytes | None:
        return super().build(data, src, append)


@dataclass
class Greedy(Construct[list]):
    """
    Represents a binary construct that builds/parses greedily.

    Parsing stops at the first element that fails to parse, and the stream is
    rewound to where that element started.
    """

    wraps: Construct

    def _size(self, ctx):
        raise SizeofError("A Greedy construct has no fixed size.")

    def _build(self, data, stream, ctx):
        for ix, element in enumerate(data):
            with scope(f"[{ix}]", stream):
                self.wraps._build(element, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        data = []
        while True:
            start = stream.tell()
            try:
                element = self.wraps._parse(stream, ctx)
            except PaboError:
                stream.seek(start)
                break
            if stream.tell() == start:
                break
            data.append(element)
        return data


@dataclass
class Sequential(Construct[list], MutableSequence):
    """
    Represents a sequence of binary constructs.
    """

    items: list[Construct]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, ix):
        return self.items[ix]

    def __setitem__(self, ix, item):
        self.items[ix] = item

    def __delitem__(self, ix):
        del self.items[ix]

    def _size(self, ctx):
        return sum(item._size(ctx) for item in self.items)

    def _build(self, data, stream, ctx):
        if len(data) != len(self.items):
            raise ValidationError(
                f"Expected {len(self.items)} elements, got {len(data)}."
            )
        built = []
        try:
            for ix, (item, element) in enumerate(zip(self.items, data, strict=True)):
                with scope(f"[{ix}]", stream):
                    built.append(item._build(element, stream, ctx))
        except Stop:
            pass
        return built

    def _parse(self, stream, ctx):
        data = []
        try:
            for ix, item in enumerate(self.items):
                with scope(f"[{ix}]", stream):
                    data.append(item._parse(stream, ctx))
        except Stop:
            pass
        return data

    def insert(self, ix: int, item: Construct) -> None:
        self.items.insert(ix, item)


@dataclass
class Repeat(Construct[list]):
    """
    Represents a binary construct repeated `count` times.
    """

    wraps: Construct
    count: Dynamic

    def _size(self, ctx):
        return self.wraps._size(ctx) * _int(self.count, ctx)

    def _build(self, data, stream, ctx):
        count = _int(self.count, ctx)
        if len(data) < count:
            raise ValidationError(f"Not enough data. Need at least {count} elements.")
        built = []
        for ix in range(count):
            with scope(f"[{ix}]", stream):
                built.append(self.wraps._build(data[ix], stream, ctx))
        return built

    def _parse(self, stream, ctx):
        count = _int(self.count, ctx)
        many = getattr(self.wraps, "_parse_many", None)
        if many is not None and count > 0:
            data = many(stream, ctx, count)
            if data is not None:
                return data
        data = []
        for ix in range(count):
            with scope(f"[{ix}]", stream):
                data.append(self.wraps._parse(stream, ctx))
        return data


@dataclass
class Adapted(Construct):
    """
    Represents a binary construct that is adaptable.

    `decode` is applied to the parsed value, and `encode` to the value before
    it is built.
    """

    wraps: Construct
    decode: Callable
    encode: Callable

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        self.wraps._build(self.encode(data), stream, ctx)
        return data

    def _parse(self, stream, ctx):
        return self.decode(self.wraps._parse(stream, ctx))


@dataclass
class Prefixed(Construct):
    """
    Represents a binary construct prefixed by its length in bytes.
    """

    pre: Int
    wraps: Construct

    def _size(self, ctx):
        raise SizeofError("A Prefixed construct has no fixed size.")

    def _build(self, data, stream, ctx):
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        payload = buffer.getvalue()
        self.pre._build(len(payload), stream, ctx)
        stream.write(payload)
        return built

    def _parse(self, stream, ctx):
        size = self.pre._parse(stream, ctx)
        return self.wraps._parse(BytesIO(read_exactly(stream, size)), ctx)


@dataclass
class Padded(Construct):
    """
    Represents a binary construct with `pad` bytes of padding.

    The padding is `fill` (a null byte by default) repeated, and goes after
    the construct (`side="right"`) or before it (`side="left"`). It is
    skipped when parsing.
    """

    pad: Dynamic
    wraps: Construct
    fill: bytes = b"\x00"
    side: Literal["right", "left"] = "right"

    def __post_init__(self):
        if len(self.fill) != 1:
            raise PaboError("The fill must be a single byte.")
        if self.side not in ("right", "left"):
            raise PaboError(f"Invalid side {self.side!r}. Must be 'right' or 'left'.")

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        return self.wraps._size(ctx) + _int(self.pad, ctx, "padding")

    def _build(self, data, stream, ctx):
        padding = self.fill * _int(self.pad, ctx, "padding")
        if self.side == "left":
            stream.write(padding)
        built = self.wraps._build(data, stream, ctx)
        if self.side == "right":
            stream.write(padding)
        return built

    def _parse(self, stream, ctx):
        if self.side == "left":
            read_exactly(stream, _int(self.pad, ctx, "padding"))
        data = self.wraps._parse(stream, ctx)
        if self.side == "right":
            read_exactly(stream, _int(self.pad, ctx, "padding"))
        return data
