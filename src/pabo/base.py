"""
Base classes.
"""

from abc import ABC
from pathlib import Path
from abc import abstractmethod
from attrs import define, field
from io import BytesIO, BufferedIOBase
from typing import Any, Union, Optional


@define
class PaboError(Exception):

    """
    Base class for all errors in pabo.
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
    def __size__(self):
        pass

    @abstractmethod
    def __build__(self, data, stream):
        pass

    @abstractmethod
    def __parse__(self, stream):
        pass

    def __truediv__(self, operand):
        if not isinstance(operand, str):
            raise PaboError(f"{operand} not a str. Cannot be used as docs.")
        self.docs = operand
        return self

    def __floordiv__(self, operand):
        return self.__truediv__(operand)

    @property
    def size(self) -> int:
        size = self.__size__()
        if isinstance(size, int):
            return size
        raise PaboError("No reasonable size was returned.")

    def build(
        self,
        data: Any,
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
            self.__build__(data, to_)
            return to_.getvalue()
        if isinstance(to_, (str, Path)):
            with open(to_, "ab") as f:
                self.__build__(data, f)
            return
        if isinstance(to_, (BytesIO, BufferedIOBase)):
            self.__build__(data, to_)
            return

    def parse(
        self,
        from_: Union[
            str,
            Path,
            bytes,
            BytesIO,
            BufferedIOBase,
        ],
    ) -> Any:
        if isinstance(from_, bytes):
            return self.__parse__(BytesIO(from_))
        if isinstance(from_, (str, Path)):
            with open(from_, "rb") as f:
                return self.__parse__(f)
        if isinstance(from_, BytesIO):
            return self.__parse__(from_)
        if isinstance(from_, BufferedIOBase):
            return self.__parse__(from_)
