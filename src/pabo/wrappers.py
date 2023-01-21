"""
Wrappers for constructs.
"""

from attrs import define
from pathlib import Path
from pabo.numeric import Int
from io import BytesIO, BufferedIOBase
from pabo.base import PaboError, Construct
from collections.abc import MutableSequence
from typing import Any, List, Union, Optional, Callable


@define
class Const(Construct):

    """
    Represents a binary construct that is constant.
    """

    value: Any
    wraps: Construct

    def __size__(self):
        return self.wraps.size

    def __build__(self, stream):
        self.wraps.__build__(self.value, stream)

    def __parse__(self, stream):
        data = self.wraps.__parse__(stream)
        if data != self.value:
            raise PaboError("Parsed value different from reference.")
        else:
            return data

    def build(
        self,
        to_: Optional[
            Union[
                str,
                Path,
                BytesIO,
                BufferedIOBase,
            ]
        ] = None,
    ) -> Optional[bytes]:
        if to_ is None:
            to_ = BytesIO()
            self.__build__(to_)
            return to_.getvalue()
        if isinstance(to_, (str, Path)):
            with open(to_, "wb") as f:
                self.__build__(f)
            return
        if isinstance(to_, (BytesIO, BufferedIOBase)):
            self.__build__(to_)
            return


@define
class Greedy(Construct):

    """
    Represents a binary construct that builds/parses greedily.
    """

    wraps: Construct

    def __size__(self):
        return self.wraps.__size__

    def __build__(self, data, stream):
        for element in data:
            self.wraps.__build__(element, stream)

    def __parse__(self, stream):
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

    def __len__(self):
        return len(self.items)

    def __getitem__(self, ix):
        return self.items[ix]

    def __setitem__(self, ix, item):
        self.items[ix] = item

    def __delitem__(self, ix):
        del self.items[ix]

    def __size__(self):
        sizes = [_.__size__() for _ in self.items]
        return sum([_ for _ in sizes if _ is not None])

    def __build__(self, data, stream):
        [
            item.__build__(element, stream)
            for (
                item,
                element,
            ) in zip(self.items, data)
        ]

    def __parse__(self, stream):
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

    def __size__(self):
        return self.wraps.size * self.count

    def __build__(self, data, stream):
        if len(data) < self.count:
            raise PaboError(f"Not enough data to build. Need at least {self.count}")
        else:
            for ix in range(self.count):
                self.wraps.__build__(data[ix], stream)

    def __parse__(self, stream):
        return [self.wraps.__parse__(stream) for _ in range(self.count)]


@define
class Adapted(Construct):

    """
    Represents a binary construct that is adaptable.
    """

    wraps: Construct
    post: Callable
    pre: Callable

    def __size__(self):
        return self.wraps.size

    def __build__(self, data, stream):
        self.wraps.__build__(self.pre(data), stream)

    def __parse__(self, stream):
        return self.post(self.wraps.__parse__(stream))


@define
class Prefixed(Construct):

    """
    Represents a binary construct with a prefix for its length.
    """

    pre: Int
    wraps: Construct

    def __size__(self):
        return self.pre.size + self.wraps.size

    def __build__(self, data, stream):
        try:
            size = len(data)
        except Exception as ERROR:
            raise PaboError("Data has no determinable size.") from ERROR
        self.pre.__build__(size, stream)
        self.wraps.__build__(data, stream)

    def __parse__(self, stream):
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

    def __size__(self):
        return self.wraps.size + self.pad

    def __build__(self, data, stream):
        if len(data) < self.wraps.size:
            raise PaboError("Not enough data to build.")
        self.wraps.__build__(data + b"\x00" * self.pad, stream)

    def __parse__(self, stream):
        data = stream.read(self.size)
        data = data.rstrip(b"\x00")
        return self.wraps.parse(data)
