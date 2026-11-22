"""
Binary parsing for dummies!
"""

from beartype.claw import beartype_this_package

beartype_this_package()

from pabo import aliases
from pabo.aliases import *  # noqa: F403
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
from pabo.debug import Probe
from pabo.declarative import Struct, StructConstruct
from pabo.errors import (
    ConstError,
    ContextError,
    PaboError,
    SizeofError,
    StreamError,
    ValidationError,
)
from pabo.bits import BitFlag, BitInt, BitPadding, Bits, BitStruct
from pabo.bytes import Bytes, Flag, GreedyBytes, Padding
from pabo.numeric import Array, Float, Int, VarInt, ZigZag
from pabo.specify import Embedded, Specification
from pabo.specify import Specification as Spec
from pabo.stream import Aligned, AlignedSpec, Lazy, LazyValue, Peek, Pointer, Seek, Tell
from pabo.strings import CString, GreedyString, Line, PaddedString, PascalString
from pabo.transforms import Checksummed, Compressed, Transformed
from pabo.wrappers import Adapted, Const, Greedy, Padded, Prefixed, Repeat, Sequential
from pabo.transforms import Checksummed, Compressed, Transformed
from pabo.wrappers import Sequential as Seq

__all__ = [
    "Probe",
    "Adapted",
    "Aligned",
    "AlignedSpec",
    "Array",
    "BitFlag",
    "BitInt",
    "BitPadding",
    "Bits",
    "BitStruct",
    "Bytes",
    "Check",
    "Checksummed",
    "Compressed",
    "Computed",
    "Const",
    "ConstError",
    "Construct",
    "Container",
    "Context",
    "ContextError",
    "CString",
    "Embedded",
    "Enum",
    "Flag",
    "FlagsEnum",
    "Float",
    "Greedy",
    "GreedyBytes",
    "GreedyString",
    "If",
    "Int",
    "Lazy",
    "LazyValue",
    "Line",
    "Optional",
    "PaboError",
    "Padded",
    "PaddedString",
    "Padding",
    "PascalString",
    "Peek",
    "Pointer",
    "Prefixed",
    "Rebuild",
    "Repeat",
    "RepeatUntil",
    "Seek",
    "Seq",
    "Sequential",
    "SizeofError",
    "Spec",
    "Specification",
    "StopIf",
    "StreamError",
    "Struct",
    "StructConstruct",
    "Switch",
    "Tell",
    "Terminated",
    "this",
    "Timestamp",
    "Transformed",
    "Validated",
    "ValidationError",
    "VarInt",
    "ZigZag",
]
__all__ += aliases.__all__
