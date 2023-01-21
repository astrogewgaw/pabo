"""
Specifications for binary data.
"""

from typing import Dict
from attrs import define
from pabo.base import PaboError, Construct


@define
class Specification(Construct):

    """
    Represents a specification for binary data.
    """

    fields: Dict[str, Construct]

    def __size__(self):
        return sum(field.size for field in self.fields.values())

    def __build__(self, data, stream):
        try:
            for (
                name,
                field,
            ) in self.fields.items():
                field.__build__(data[name], stream)
        except KeyError:
            raise PaboError("Data not according to specification.")

    def __parse__(self, stream):
        return {
            name: field.__parse__(stream)
            for (
                name,
                field,
            ) in self.fields.items()
        }
