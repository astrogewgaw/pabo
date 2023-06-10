"""
String constructs.
"""

from attrs import define
from pabo.bytes import Bytes
from pabo.numeric import Int
from pabo.base import PaboError, Construct
from pabo.wrappers import Padded, Prefixed


@define
class CString(Construct):

    """
    Represents a C-style string.
    """

    code: str = "utf-8"

    def __size__(self):
        raise PaboError("A CString has no fixed size.")

    def __build__(self, data, stream) -> None:
        raw = data.encode(self.code)
        raw = b"".join([raw, b"\x00"])
        stream.write(raw)

    def __parse__(self, stream):
        data = []
        while True:
            raw = stream.read(1)
            if not raw:
                raise PaboError("Premature end of stream.")
            if raw != b"\x00":
                data.append(raw)
            else:
                break
        data = b"".join(data)
        data = data.decode(self.code)
        return data


@define
class PascalString(Construct):

    """
    Represents a Pascal-style string.
    """

    pre: Int
    code: str = "utf-8"

    def __size__(self):
        raise PaboError("A PascalString has no fixed size.")

    def __build__(self, data, stream) -> None:
        raw = data.encode(self.code)
        Prefixed(self.pre, Bytes(-1)).__build__(raw, stream)

    def __parse__(self, stream):
        return Prefixed(self.pre, Bytes(-1)).__parse__(stream).decode(self.code)


@define
class PaddedString(Construct):

    """
    Represents a string padded by null bytes (\x00).
    """

    size: int
    code: str = "utf-8"

    def __size__(self):
        return self.size

    def __build__(self, data, stream) -> None:
        raw = data.encode(self.code)
        pad = self.size - len(raw)
        Padded(pad, Bytes(len(raw))).__build__(raw, stream)

    def __parse__(self, stream):
        raw = stream.read(self.size)
        raw = raw.rstrip(b"\x00")
        data = raw.decode(self.code)
        return data


@define
class Line(Construct):

    """
    Represents a string ending with a CRLF (b'\r\n').
    """

    code: str = "utf-8"

    def __size__(self):
        raise PaboError("A Line has no fixed size!")

    def __build__(self, data, stream):
        raw = data.encode(self.code)
        stream.write(b"".join([raw, b"\r\n"]))

    def __parse__(self, stream):
        data = []
        while True:
            raw = stream.read(1)
            if not raw:
                raise PaboError("Premature end of stream.")
            if data[-2:] != b"\r\n":
                data.append(raw)
            else:
                break
        data = b"".join(data[:-2])
        data = data.decode(self.code)
        return data
