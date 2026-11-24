"""
Wrappers for constructs.
"""

from collections.abc import Callable, MutableSequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pabo.base import Construct, Stop, readexact, scope
from pabo.errors import ConstError, PaboError, SizeofError, ValidationError, attempt
from pabo.expressions import evaluate
from pabo.hints import Dynamic, Side, Target


def _int(value, ctx, what: str = "count") -> int:
    value = evaluate(value, ctx)
    if not isinstance(value, int):
        raise PaboError(f"THE {what} MUST BE AN INTEGER, GOT {value!r}.")
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
            raise ConstError(f"CANNOT BUILD {data!r}: THE CONSTANT IS {self.value!r}.")
        self.wraps._build(self.value, stream, ctx)
        return self.value

    def _parse(self, stream, ctx):
        data = self.wraps._parse(stream, ctx)
        if data != self.value:
            raise ConstError(
                f"PARSED {data!r}, BUT EXPECTED THE CONSTANT {self.value!r}."
            )
        return data

    def build(
        self, data: Any = None, src: Target = None, append: bool = False
    ) -> bytes | None:
        """
        Build the constant (`data` may be left out).
        """

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
        raise SizeofError("A GREEDY CONSTRUCT HAS NO FIXED SIZE.")

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
    Represents a sequence of unnamed binary constructs, parsed into a list.

    It behaves like a list of constructs, so items can be added or removed.
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
                f"EXPECTED {len(self.items)} ELEMENTS, GOT {len(data)}."
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
        """
        Insert a construct before position `ix`.
        """

        self.items.insert(ix, item)


@dataclass
class Repeat(Construct[list]):
    """
    Represents a binary construct repeated `count` times, as a list.

    `count` may depend on other fields (`Repeat(pb.u16, this.n)`). For numbers,
    `Array` is faster and gives a numpy array instead.
    """

    wraps: Construct
    count: Dynamic

    def _size(self, ctx):
        return self.wraps._size(ctx) * _int(self.count, ctx)

    def _build(self, data, stream, ctx):
        count = _int(self.count, ctx)
        if len(data) < count:
            raise ValidationError(f"NOT ENOUGH DATA. NEED AT LEAST {count} ELEMENTS.")
        many = getattr(self.wraps, "_buildmany", None)
        if many is not None and count > 0:
            built = many(data[:count], stream, ctx)
            if built is not None:
                return built
        built = []
        for ix in range(count):
            with scope(f"[{ix}]", stream):
                built.append(self.wraps._build(data[ix], stream, ctx))
        return built

    def _parse(self, stream, ctx):
        count = _int(self.count, ctx)
        many = getattr(self.wraps, "_parsemany", None)
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
    it is built. If either raises an exception, it becomes a `ValidationError`.
    """

    wraps: Construct
    decode: Callable[[Any], Any]
    encode: Callable[[Any], Any]

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        self.wraps._build(attempt(self.encode, data), stream, ctx)
        return data

    def _parse(self, stream, ctx):
        return attempt(self.decode, self.wraps._parse(stream, ctx))


@dataclass
class Prefixed(Construct):
    """
    Represents a binary construct prefixed by its length in bytes.

    `pre` is the construct holding the length: a fixed-size integer such as
    `pb.u16`, or a variable-length one such as `pb.VarInt()`. When parsing,
    exactly that many bytes are read and `wraps` is parsed from them, so
    `wraps` may be greedy (`Bytes(-1)`, `Array(...)`). When building, the
    length is computed.
    """

    pre: Construct
    wraps: Construct

    def _size(self, ctx):
        raise SizeofError("A PREFIXED CONSTRUCT HAS NO FIXED SIZE.")

    def _build(self, data, stream, ctx):
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        payload = buffer.getvalue()
        self.pre._build(len(payload), stream, ctx)
        stream.write(payload)
        return built

    def _parse(self, stream, ctx):
        size = self.pre._parse(stream, ctx)
        if not isinstance(size, int) or size < 0:
            raise ValidationError(
                f"THE LENGTH PREFIX MUST BE A NON-NEGATIVE INT, GOT {size!r}."
            )
        return self.wraps._parse(BytesIO(readexact(stream, size)), ctx)


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
    side: Side = "right"

    def __post_init__(self):
        if len(self.fill) != 1:
            raise PaboError("THE FILL MUST BE A SINGLE BYTE.")
        if self.side not in ("right", "left"):
            raise PaboError(f"INVALID SIDE {self.side!r}. MUST BE 'right' OR 'left'.")

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
            readexact(stream, _int(self.pad, ctx, "padding"))
        data = self.wraps._parse(stream, ctx)
        if self.side == "right":
            readexact(stream, _int(self.pad, ctx, "padding"))
        return data
