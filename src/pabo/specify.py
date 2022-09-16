"""
Specifications for binary data.
"""

from attrs import define
from collections.abc import MutableMapping
from pabo.base import PaboError, Construct
from typing import IO, Any, Dict, Iterable


@define
class Specification(Construct, MutableMapping):

    """
    Represents a specification for binary data.
    """

    fields: Dict[str, Construct]

    def __len__(self) -> int:
        return len(self.fields)

    def __iter__(self) -> Iterable:
        return iter(self.fields)

    def __getitem__(self, key: str) -> Construct:
        return self.fields[key]

    def __setitem__(self, key: str, item: Construct) -> None:
        self.fields[key] = item

    def __delitem__(self, key: str) -> None:
        del self.fields[key]

    def __size__(self) -> int:
        return sum(field.size for field in self.fields.values())

    def __build__(
        self,
        data: Dict[str, Any],
        stream: IO[bytes],
    ) -> None:
        try:
            for (
                name,
                field,
            ) in self.fields.items():
                field.__build__(data[name], stream)
        except KeyError as ERROR:
            raise PaboError("Data not according to specification.") from ERROR

    def __parse__(self, stream: IO[bytes]) -> Dict[str, Any]:
        return {
            name: field.__parse__(stream)
            for (
                name,
                field,
            ) in self.fields.items()
        }
