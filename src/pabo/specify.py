"""
Specifications for binary data.
"""

from dataclasses import dataclass

from pabo.base import Construct, PaboError
from pabo.wrappers import Const


@dataclass
class Specification(Construct):
    """
    Represents a specification for binary data.
    """

    fields: dict[str, Construct]

    def _size(self):
        return sum(field.size for field in self.fields.values())

    def _build(self, data, stream):
        for name, field in self.fields.items():
            if name in data:
                value = data[name]
            elif isinstance(field, Const):
                value = None
            else:
                raise PaboError(
                    f"Missing field {name!r}. Data not according to specification."
                )
            field._build(value, stream)

    def _parse(self, stream):
        return {name: field._parse(stream) for name, field in self.fields.items()}
