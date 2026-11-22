"""
Binary parsing for dummies!
"""

from beartype.claw import beartype_this_package

beartype_this_package()

from pabo.adapters import Enum, FlagsEnum, Timestamp
from pabo.base import Construct
from pabo.control import (
    Check,
    Computed,
    If,
    Optional,
    Rebuild,
    RepeatUntil,
    StopIf,
    Switch,
    Terminated,
    Validated,
)
from pabo.context import Container, Context, this
from pabo.errors import (
    ConstError,
    ContextError,
    PaboError,
    SizeofError,
    StreamError,
    ValidationError,
)
from pabo.bits import Bits
from pabo.bytes import Bytes, Flag, GreedyBytes, Padding
from pabo.numeric import Array, Float, Int, VarInt, ZigZag
from pabo.specify import Specification
from pabo.specify import Specification as Spec
from pabo.strings import CString, GreedyString, Line, PaddedString, PascalString
from pabo.wrappers import Adapted, Const, Greedy, Padded, Prefixed, Repeat, Sequential
from pabo.wrappers import Sequential as Seq

__all__ = [
    "Adapted",
    "Array",
    "Bits",
    "Bytes",
    "Check",
    "Computed",
    "Const",
    "ConstError",
    "Construct",
    "Container",
    "Context",
    "ContextError",
    "CString",
    "Enum",
    "Flag",
    "FlagsEnum",
    "Float",
    "Greedy",
    "GreedyBytes",
    "GreedyString",
    "If",
    "Int",
    "Line",
    "Optional",
    "PaboError",
    "Padded",
    "PaddedString",
    "Padding",
    "PascalString",
    "Prefixed",
    "Rebuild",
    "Repeat",
    "RepeatUntil",
    "Seq",
    "Sequential",
    "SizeofError",
    "Spec",
    "Specification",
    "StopIf",
    "StreamError",
    "Switch",
    "Terminated",
    "this",
    "Timestamp",
    "Validated",
    "ValidationError",
    "VarInt",
    "ZigZag",
]
