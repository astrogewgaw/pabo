"""
Base classes.
"""

from abc import ABC
from io import BytesIO
from typing import IO, Any
from abc import abstractmethod
from attrs import define, field
from importlib import import_module


@define
class PaboError(Exception):

    """
    Base class for all error in pabo.
    """

    def __init__(self, msg: str):
        super().__init__(f"바보! {msg}")


@define
class Construct(ABC):

    """
    Abstract base class for all binary constructs.

    This class implements the basic functinality required by all binary
    constructs. When creating a new construct, the user has to implement
    just 3 magic methods: `__size__`, `__parse__`, and `__build__`. The
    user may look at the constructs already implemented in this package
    for inspiration.
    """

    docs: str = field(kw_only=True, default="")

    @abstractmethod
    def __size__(self) -> int:
        pass

    @abstractmethod
    def __build__(
        self,
        data: Any,
        stream: IO[bytes],
    ) -> None:
        pass

    @abstractmethod
    def __parse__(self, stream: IO[bytes]) -> Any:
        pass

    def __mul__(self, count: int):
        if isinstance(count, int):
            return getattr(
                import_module("pabo.wrappers"),
                "Repeat",
            )(self, count)
        else:
            raise PaboError("A Construct may only be multiplied by an integer.")

    def __rmul__(self, count: int):
        return self.__mul__(count)

    def __truediv__(self, docs: str):
        self.docs = docs
        return self

    def __floordiv__(self, docs: str):
        self.docs = docs
        return self

    @property
    def size(self) -> int:

        """
        The size of the construct.
        """

        return self.__size__()

    def build_stream(
        self,
        data: Any,
        stream: IO[bytes],
    ) -> None:

        """
        Build data into a stream.
        """

        self.__build__(data, stream)

    def parse_stream(self, stream: IO[bytes]) -> Any:

        """
        Parse data from a stream.
        """

        return self.__parse__(stream)

    def build(self, data: Any) -> bytes:

        """
        Build and return data as bytes.
        """

        stream = BytesIO()
        self.build_stream(data, stream)
        return stream.getvalue()

    def parse(self, data: bytes) -> Any:

        """
        Parse bytes and return the result.
        """

        stream = BytesIO(data)
        return self.parse_stream(stream)
