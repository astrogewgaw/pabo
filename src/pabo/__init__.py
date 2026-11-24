"""
Binary parsing for dummies!

Type hints on pabo's own functions are checked at runtime by beartype. Set
the environment variable `PABOROAR=0` before importing pabo to turn
this off, which makes parsing in tight loops a little faster.
"""

import os
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("pabo")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"

if os.environ.get("PABOROAR", "1") != "0":
    from beartype.claw import beartype_this_package

    beartype_this_package()

from pabo import aliases
from pabo.adapters import Enum, FlagsEnum, Timestamp
from pabo.aliases import *
from pabo.base import Construct
from pabo.bits import BitFlag, BitInt, BitPadding, Bits, BitStruct
from pabo.bytes import Bytes, Flag, GreedyBytes, Padding
from pabo.context import Container, Context
from pabo.control import (
    Check,
    Computed,
    Deferred,
    If,
    Optional,
    Rebuild,
    RepeatUntil,
    Select,
    StopIf,
    Switch,
    Terminated,
    Union,
    Validated,
)
from pabo.debug import Debug, Probe
from pabo.declarative import Struct, StructConstruct
from pabo.errors import (
    ConstError,
    ContextError,
    PaboError,
    SizeofError,
    StreamError,
    ValidationError,
)
from pabo.expressions import Expr, This, lenof, this
from pabo.numeric import Array, Float, Int, VarInt, ZigZag
from pabo.specify import Embedded, Focused, Specification
from pabo.specify import Specification as Spec
from pabo.stream import (
    Aligned,
    AlignedSpec,
    Lazy,
    LazyValue,
    Peek,
    Pointer,
    Remaining,
    Seek,
    Tell,
)
from pabo.strings import CString, GreedyString, Line, PaddedString, PascalString
from pabo.transforms import Checksummed, Compressed, Transformed
from pabo.wrappers import (
    Adapted,
    Const,
    Default,
    Delimited,
    FixedSized,
    Greedy,
    Padded,
    Prefixed,
    PrefixedArray,
    Repeat,
    Sequential,
)
from pabo.wrappers import Sequential as Seq

__all__ = [
    "Adapted",
    "Aligned",
    "AlignedSpec",
    "Array",
    "BitFlag",
    "BitInt",
    "BitPadding",
    "BitStruct",
    "Bits",
    "Bytes",
    "CString",
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
    "Debug",
    "Default",
    "Deferred",
    "Delimited",
    "Embedded",
    "Enum",
    "Expr",
    "FixedSized",
    "Flag",
    "FlagsEnum",
    "Float",
    "Focused",
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
    "PrefixedArray",
    "Probe",
    "Rebuild",
    "Remaining",
    "Repeat",
    "RepeatUntil",
    "Seek",
    "Select",
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
    "This",
    "Timestamp",
    "Transformed",
    "Union",
    "Validated",
    "ValidationError",
    "VarInt",
    "ZigZag",
    "__version__",
    "lenof",
    "this",
]
__all__ += aliases.__all__
