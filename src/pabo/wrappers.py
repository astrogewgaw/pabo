"""
Wrappers for constructs.
"""

from io import BytesIO
from attrs import define
from pabo.numbers import Int
from pabo.base import PaboError, Construct
from typing import IO, Any, List, Callable
from collections.abc import MutableSequence


@define
class Const(Construct):

    """
    Represents a binary construct that is constant.
    """

    value: Any
    wraps: Construct

    def __size__(self) -> int:
        return self.wraps.size

    def __build__(self, stream: IO[bytes]) -> None:
        self.wraps.__build__(self.value, stream)

    def __parse__(self, stream: IO[bytes]) -> Any:
        data = self.wraps.__parse__(stream)
        if data != self.value:
            raise PaboError("Parsed value different from reference.")
        else:
            return data

    def build_stream(self, stream: IO[bytes]) -> None:
        self.__build__(stream)

    def build(self) -> bytes:
        stream = BytesIO()
        self.__build__(stream)
        return stream.getvalue()


@define
class Greedy(Construct):

    """
    Represents a binary construct that builds/parses greedily.
    """

    wraps: Construct

    def __size__(self):
        return self.wraps.__size__

    def __build__(
        self,
        data: List[Any],
        stream: IO[bytes],
    ) -> None:
        for element in data:
            self.wraps.__build__(element, stream)

    def __parse__(self, stream: IO[bytes]) -> List[Any]:
        data = []
        while True:
            try:
                data.append(self.wraps.__parse__(stream))
            except Exception:
                break
        return data


@define
class Sequential(Construct, MutableSequence):

    """
    Represents a sequence of binary constructs.
    """

    items: List[Construct]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, ix: int) -> Construct:
        return self.items[ix]

    def __setitem__(self, ix: int, item: Construct) -> None:
        self.items[ix] = item

    def __delitem__(self, ix: int) -> None:
        del self.items[ix]

    def __size__(self) -> int:
        sizes = [_.__size__() for _ in self.items]
        return sum([_ for _ in sizes if _ is not None])

    def __build__(
        self,
        data: List[Any],
        stream: IO[bytes],
    ) -> None:
        [
            item.__build__(element, stream)
            for (
                item,
                element,
            ) in zip(self.items, data)
        ]

    def __parse__(self, stream: IO[bytes]) -> List[Any]:
        return [item.__parse__(stream) for item in self.items]

    def insert(self, ix: int, item: Construct) -> None:
        self.items.insert(ix, item)


@define
class Repeat(Construct):

    """
    Represents a binary construct repeated.
    """

    wraps: Construct
    count: int

    def __size__(self) -> int:
        return self.wraps.__size__() * self.count

    def __build__(
        self,
        data: List[Any],
        stream: IO[bytes],
    ) -> None:
        if len(data) < self.count:
            raise PaboError(f"Not enough data to build. Need at least {self.count}")
        else:
            for ix in range(self.count):
                self.wraps.__build__(data[ix], stream)

    def __parse__(self, stream: IO[bytes]) -> List[Any]:
        return [self.wraps.__parse__(stream) for _ in range(self.count)]


@define
class Adapted(Construct):

    """
    Represents a binary construct that is adaptable.
    """

    wraps: Construct
    post: Callable
    pre: Callable

    def __size__(self) -> int:
        return self.wraps.size

    def __build__(
        self,
        data: Any,
        stream: IO[bytes],
    ) -> None:
        self.wraps.__build__(self.pre(data), stream)

    def __parse__(self, stream: IO[bytes]) -> Any:
        return self.post(self.wraps.__parse__(stream))


@define
class Prefixed(Construct):

    """
    Represents a binary construct with a prefix for its length.
    """

    pre: Int
    wraps: Construct

    def __size__(self) -> int:
        return self.pre.size + self.wraps.size

    def __build__(
        self,
        data: Any,
        stream: IO[bytes],
    ) -> None:
        try:
            size = len(data)
        except Exception as ERROR:
            raise PaboError("Data has no determinable size.") from ERROR
        self.pre.__build__(size, stream)
        self.wraps.__build__(data, stream)

    def __parse__(self, stream: IO[bytes]) -> Any:
        size = self.pre.__parse__(stream)
        data = stream.read(size)
        return self.wraps.parse(data)


@define
class Padded(Construct):

    """
    Represents a binary construct padded with null bytes (\x00).
    """

    pad: int
    wraps: Construct

    def __size__(self) -> int:
        return self.wraps.size + self.pad

    def __build__(
        self,
        data: Any,
        stream: IO[bytes],
    ) -> None:
        if len(data) < self.wraps.size:
            raise PaboError("Not enough data to build.")
        data = self.wraps.build(data)
        data = data.ljust(self.size, b"\x00")
        stream.write(data)

    def __parse__(self, stream: IO[bytes]) -> Any:
        data = stream.read(self.size)
        data = data.rstrip(b"\x00")
        return self.wraps.parse(data)
