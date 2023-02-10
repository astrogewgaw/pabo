"""
Base classes.
"""

from abc import ABC
from io import BytesIO
from pathlib import Path
from abc import abstractmethod
from attrs import define, field


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

    def build(self, data, src=None):
        if src is None:
            src = BytesIO()
            self.__build__(data, src)
            return src.getvalue()
        if isinstance(src, (str, Path)):
            with open(src, "ab") as f:
                return self.__build__(data, f)
        return self.__build__(data, src)

    def parse(self, dst):
        if isinstance(dst, bytes):
            return self.__parse__(BytesIO(dst))
        if isinstance(dst, (str, Path)):
            with open(dst, "rb") as f:
                return self.__parse__(f)
        return self.__parse__(dst)
