"""
Binary parsing for dummies!
"""

from beartype.claw import beartype_this_package

beartype_this_package()

from pabo.base import Construct, PaboError
from pabo.bits import Bits
from pabo.bytes import Bytes, Flag, Padding
from pabo.numeric import Array, Float, Int
from pabo.specify import Specification
from pabo.specify import Specification as Spec
from pabo.strings import CString, Line, PaddedString, PascalString
from pabo.wrappers import Adapted, Const, Greedy, Padded, Prefixed, Repeat, Sequential
from pabo.wrappers import Sequential as Seq

__all__ = [
    "Adapted",
    "Array",
    "Bits",
    "Bytes",
    "CString",
    "Const",
    "Construct",
    "Flag",
    "Float",
    "Greedy",
    "Int",
    "Line",
    "PaboError",
    "Padded",
    "PaddedString",
    "Padding",
    "PascalString",
    "Prefixed",
    "Repeat",
    "Seq",
    "Sequential",
    "Spec",
    "Specification",
]
