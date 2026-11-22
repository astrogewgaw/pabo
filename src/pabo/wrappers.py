"""
Wrappers for constructs.
"""

from collections.abc import Callable, MutableSequence
from dataclasses import dataclass
from typing import Any

from pabo.base import Construct, PaboError, read_exactly
from pabo.numeric import Int


@dataclass
class Const(Construct):
    """
    Represents a binary construct that is constant.

    When building, the value may be omitted (None); it is filled in automatically.
    """

    value: Any
    wraps: Construct

    def _size(self):
        return self.wraps.size

    def _build(self, data, stream):
        if data is not None and data != self.value:
            raise PaboError(f"Cannot build {data!r}: the constant is {self.value!r}.")
        self.wraps._build(self.value, stream)

    def _parse(self, stream):
        data = self.wraps._parse(stream)
        if data != self.value:
            raise PaboError(
                f"Parsed {data!r}, but expected the constant {self.value!r}."
            )
        return data

    def build(self, data=None, src=None, append: bool = False) -> bytes | None:
        return super().build(data, src, append)


@dataclass
class Greedy(Construct):
    """
    Represents a binary construct that builds/parses greedily.

    Parsing stops at the first element that fails to parse, and the stream is
    rewound to where that element started.
    """

    wraps: Construct

    def _size(self):
        raise PaboError("A Greedy construct has no fixed size.")

    def _build(self, data, stream):
        for element in data:
            self.wraps._build(element, stream)

    def _parse(self, stream):
        data = []
        while True:
            start = stream.tell()
            try:
                element = self.wraps._parse(stream)
            except PaboError:
                stream.seek(start)
                break
            if stream.tell() == start:
                break
            data.append(element)
        return data


@dataclass
class Sequential(Construct, MutableSequence):
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

    def _size(self):
        return sum(item.size for item in self.items)

    def _build(self, data, stream):
        if len(data) != len(self.items):
            raise PaboError(f"Expected {len(self.items)} elements, got {len(data)}.")
        for item, element in zip(self.items, data, strict=True):
            item._build(element, stream)

    def _parse(self, stream):
        return [item._parse(stream) for item in self.items]

    def insert(self, ix: int, item: Construct) -> None:
        self.items.insert(ix, item)


@dataclass
class Repeat(Construct):
    """
    Represents a binary construct repeated.
    """

    wraps: Construct
    count: int

    def _size(self):
        return self.wraps.size * self.count

    def _build(self, data, stream):
        if len(data) < self.count:
            raise PaboError(f"Not enough data. Need at least {self.count} elements.")
        for ix in range(self.count):
            self.wraps._build(data[ix], stream)

    def _parse(self, stream):
        return [self.wraps._parse(stream) for _ in range(self.count)]


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

    def _size(self):
        return self.wraps.size

    def _build(self, data, stream):
        self.wraps._build(self.encode(data), stream)

    def _parse(self, stream):
        return self.decode(self.wraps._parse(stream))


@dataclass
class Prefixed(Construct):
    """
    Represents a binary construct prefixed by its length in bytes.
    """

    pre: Int
    wraps: Construct

    def _size(self):
        return self.pre.size + self.wraps.size

    def _build(self, data, stream):
        payload = self.wraps.build(data)
        self.pre._build(len(payload), stream)
        stream.write(payload)

    def _parse(self, stream):
        size = self.pre._parse(stream)
        return self.wraps.parse(read_exactly(stream, size))


@dataclass
class Padded(Construct):
    """
    Represents a binary construct followed by `pad` null bytes (\x00).
    """

    pad: int
    wraps: Construct

    def _size(self):
        return self.wraps.size + self.pad

    def _build(self, data, stream):
        self.wraps._build(data, stream)
        stream.write(b"\x00" * self.pad)

    def _parse(self, stream):
        data = self.wraps._parse(stream)
        read_exactly(stream, self.pad)
        return data
