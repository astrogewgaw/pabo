from typing import Annotated

import numpy
from numpy.typing import NDArray

def unpack(
    x: Annotated[NDArray[numpy.uint8], dict(order="C", writable=False)],
    nbits: int,
    bitorder: str = "big",
    parallel: bool = False,
) -> Annotated[NDArray[numpy.uint8], dict(order="C")]:
    """Unpack 1, 2 and 4-bit data from an 8-bit numpy array"""

def pack(
    x: Annotated[NDArray[numpy.uint8], dict(order="C", writable=False)],
    nbits: int,
    bitorder: str = "big",
    parallel: bool = False,
) -> Annotated[NDArray[numpy.uint8], dict(order="C")]:
    """Pack 1, 2 and 4-bit data into an 8-bit numpy array"""
