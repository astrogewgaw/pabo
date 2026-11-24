"""
Wrappers for constructs.
"""

from collections.abc import Callable, MutableSequence
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pabo.base import Construct, Stop, readexact, scope, tell
from pabo.errors import (
    ConstError,
    PaboError,
    SizeofError,
    StreamError,
    ValidationError,
    attempt,
)
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
class Default(Construct):
    """
    `wraps`, which may be left out when building: `value` (or, if it is a
    function, `value(ctx)`) is built instead of a missing or None value.
    """

    wraps: Construct
    value: Any

    def _omittable(self):
        return True

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        if data is None:
            data = evaluate(self.value, ctx)
        return self.wraps._build(data, stream, ctx)

    def _parse(self, stream, ctx):
        return self.wraps._parse(stream, ctx)


@dataclass
class Greedy(Construct[list]):
    """
    Represents a binary construct that builds/parses greedily.

    Parsing stops at the first element that fails to parse, and the stream is
    rewound to where that element started, or after `maximum` elements (if
    given). Fewer than `minimum` elements raise a `ValidationError`, when
    parsing and when building, as do more than `maximum` when building.
    """

    wraps: Construct
    minimum: int = 0
    maximum: int | None = None

    def __post_init__(self):
        if self.minimum < 0 or (
            self.maximum is not None and self.maximum < self.minimum
        ):
            raise PaboError(
                f"INVALID BOUNDS: minimum={self.minimum}, maximum={self.maximum}."
            )

    def _size(self, ctx):
        raise SizeofError("A GREEDY CONSTRUCT HAS NO FIXED SIZE.")

    def _bounds(self, count: int) -> None:
        if count < self.minimum:
            raise ValidationError(
                f"EXPECTED AT LEAST {self.minimum} ELEMENTS, GOT {count}."
            )
        if self.maximum is not None and count > self.maximum:
            raise ValidationError(
                f"EXPECTED AT MOST {self.maximum} ELEMENTS, GOT {count}."
            )

    def _build(self, data, stream, ctx):
        self._bounds(len(data))
        attrs, previous = ctx.__dict__, ctx.__dict__.get("_index")
        try:
            for ix, element in enumerate(data):
                attrs["_index"] = ix
                with scope(f"[{ix}]", stream):
                    self.wraps._build(element, stream, ctx)
        finally:
            attrs["_index"] = previous
        return data

    def _parse(self, stream, ctx):
        data = []
        attrs, previous = ctx.__dict__, ctx.__dict__.get("_index")
        try:
            while self.maximum is None or len(data) < self.maximum:
                attrs["_index"] = len(data)
                start = stream.tell()
                try:
                    element = self.wraps._parse(stream, ctx)
                except PaboError:
                    stream.seek(start)
                    break
                if stream.tell() == start:
                    break
                data.append(element)
        finally:
            attrs["_index"] = previous
        self._bounds(len(data))
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

    `count` may depend on other fields (`Repeat(pb.u16, this.n)`). Each element
    can read its position in the list as `this._index` (or `ctx._index`), as in
    `Greedy` and `RepeatUntil`. For numbers,
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
        attrs, previous = ctx.__dict__, ctx.__dict__.get("_index")
        try:
            for ix in range(count):
                attrs["_index"] = ix
                with scope(f"[{ix}]", stream):
                    built.append(self.wraps._build(data[ix], stream, ctx))
        finally:
            attrs["_index"] = previous
        return built

    def _parse(self, stream, ctx):
        count = _int(self.count, ctx)
        many = getattr(self.wraps, "_parsemany", None)
        if many is not None and count > 0:
            data = many(stream, ctx, count)
            if data is not None:
                return data
        data = []
        attrs, previous = ctx.__dict__, ctx.__dict__.get("_index")
        try:
            for ix in range(count):
                attrs["_index"] = ix
                with scope(f"[{ix}]", stream):
                    data.append(self.wraps._parse(stream, ctx))
        finally:
            attrs["_index"] = previous
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


def _readto(stream, term: bytes) -> tuple[bytes, bool]:
    """
    Read up to and past the first `term`, and return the bytes before it and
    whether it was found (if not, the stream is left at its end).

    Seekable streams are searched in chunks; others are read byte by byte.
    """

    start = tell(stream)
    if start is None:
        data = bytearray()
        while not data.endswith(term):
            byte = stream.read(1)
            if not byte:
                return bytes(data), False
            data += byte
        return bytes(data[: -len(term)]), True
    data = bytearray()
    while True:
        chunk = stream.read(4096)
        if not chunk:
            return bytes(data), False
        searched = max(0, len(data) - len(term) + 1)
        data += chunk
        found = data.find(term, searched)
        if found >= 0:
            stream.seek(start + found + len(term))
            return bytes(data[:found]), True


@dataclass
class Delimited(Construct):
    """
    Represents a binary construct ending at the first `term` (one or more bytes).

    When parsing, the bytes before the terminator are read and `wraps` is
    parsed from them, so it is usually greedy: `GreedyBytes()`, or
    `GreedyString()` for text. `include` keeps the terminator at the end of
    those bytes, `consume=False` leaves it in the stream for the next field,
    and `eos=True` lets the end of the stream stand in for the terminator.

    When building, the terminator is written after `wraps` (unless
    `consume=False`: then the next field writes it), and the data may not
    contain it. With `include`, the data must end with it.
    """

    wraps: Construct
    term: bytes = b"\x00"
    include: bool = False
    consume: bool = True
    eos: bool = False

    def __post_init__(self):
        if not self.term:
            raise PaboError("THE TERMINATOR MUST BE AT LEAST ONE BYTE.")

    def _size(self, ctx):
        raise SizeofError("A DELIMITED CONSTRUCT HAS NO FIXED SIZE.")

    def _build(self, data, stream, ctx):
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        raw = buffer.getvalue()
        if self.include:
            if not raw.endswith(self.term):
                raise ValidationError(
                    f"THE DATA MUST END WITH THE TERMINATOR {self.term!r}."
                )
            raw = raw[: -len(self.term)]
        if self.term in raw:
            raise ValidationError(f"THE DATA CONTAINS THE TERMINATOR {self.term!r}.")
        stream.write(raw + self.term if self.consume else raw)
        return built

    def _parse(self, stream, ctx):
        if not self.consume and tell(stream) is None:
            raise StreamError(
                "CANNOT LEAVE THE TERMINATOR ON A STREAM THAT CANNOT SEEK."
            )
        raw, found = _readto(stream, self.term)
        if not found and not self.eos:
            raise StreamError(f"THE STREAM ENDED BEFORE THE TERMINATOR {self.term!r}.")
        if found and not self.consume:
            stream.seek(stream.tell() - len(self.term))
        if found and self.include:
            raw += self.term
        return self.wraps._parse(BytesIO(raw), ctx)


@dataclass
class FixedSized(Construct):
    """
    Represents a binary construct inside a window of exactly `length` bytes.

    When parsing, `length` bytes are read and `wraps` is parsed from them; the
    bytes it doesn't use (such as the reserved tail of a C struct) are skipped.
    When building, `wraps` is padded with `fill` up to `length` bytes, and may
    not be longer. Unlike `Padded`, which adds a number of bytes, this pads to
    a total, so its size is always `length`, even if `wraps` varies in size.
    """

    length: Dynamic
    wraps: Construct
    fill: bytes = b"\x00"

    def __post_init__(self):
        if len(self.fill) != 1:
            raise PaboError("THE FILL MUST BE A SINGLE BYTE.")

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        return _int(self.length, ctx, "length")

    def _build(self, data, stream, ctx):
        length = _int(self.length, ctx, "length")
        buffer = BytesIO()
        built = self.wraps._build(data, buffer, ctx)
        raw = buffer.getvalue()
        if len(raw) > length:
            raise ValidationError(
                f"THE DATA TAKES {len(raw)} BYTES, MORE THAN THE {length} AVAILABLE."
            )
        stream.write(raw + self.fill * (length - len(raw)))
        return built

    def _parse(self, stream, ctx):
        length = _int(self.length, ctx, "length")
        return self.wraps._parse(BytesIO(readexact(stream, length)), ctx)


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
