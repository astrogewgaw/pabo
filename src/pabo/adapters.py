"""
Adapters that turn raw values into richer Python objects.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum as PyEnum
from enum import IntFlag
from fractions import Fraction
from typing import Literal

from pabo.base import Construct
from pabo.errors import PaboError, ValidationError
from pabo.numeric import Int, VarInt, ZigZag

#: Where each named epoch starts, and its default unit.
EPOCHS = {
    "unix": (datetime(1970, 1, 1, tzinfo=timezone.utc), "s"),
    "mjd": (datetime(1858, 11, 17, tzinfo=timezone.utc), "day"),
}

#: The length of each unit, in microseconds (exact, so no precision is lost).
UNITS = {
    "s": Fraction(10**6),
    "ms": Fraction(10**3),
    "us": Fraction(1),
    "ns": Fraction(1, 1000),
    "day": Fraction(86400 * 10**6),
}

Epoch = Literal["unix", "mjd"] | datetime
Unit = Literal["s", "ms", "us", "ns", "day"]


@dataclass
class Enum(Construct):
    """
    Map the integers parsed by `wraps` to members of an `enum.Enum`.

    Parsing a value that is not a member raises a `ValidationError`. Building
    accepts a member, its value, or its name.
    """

    wraps: Construct
    enum: type[PyEnum]

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _member(self, data) -> PyEnum:
        try:
            if isinstance(data, str) and not isinstance(data, self.enum):
                return self.enum[data]
            return self.enum(data)
        except (KeyError, ValueError):
            raise ValidationError(
                f"{data!r} IS NOT A MEMBER OF {self.enum.__name__}."
            ) from None

    def _build(self, data, stream, ctx):
        member = self._member(data)
        self.wraps._build(member.value, stream, ctx)
        return member

    def _parse(self, stream, ctx):
        return self._member(self.wraps._parse(stream, ctx))


@dataclass
class FlagsEnum(Construct):
    """
    Map the integers parsed by `wraps` to an `enum.IntFlag` (a set of bit flags).

    Building accepts a flag value or a plain int.
    """

    wraps: Construct
    flags: type[IntFlag]

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        flags = self.flags(int(data))
        self.wraps._build(int(flags), stream, ctx)
        return flags

    def _parse(self, stream, ctx):
        return self.flags(self.wraps._parse(stream, ctx))


@dataclass
class Timestamp(Construct[datetime]):
    """
    Map the numbers parsed by `wraps` to timezone-aware (UTC) datetimes.

    `epoch` is "unix" (1970-01-01), "mjd" (Modified Julian Date: 1858-11-17) or a
    datetime. `unit` is what one tick counts: "s", "ms", "us", "ns" or "day". It
    defaults to "s" for "unix" and for datetimes, and to "day" for "mjd", but
    many formats store Unix time in milliseconds, microseconds or nanoseconds.
    Datetimes only resolve microseconds, so nanoseconds are rounded. When
    building into an integer, the value is rounded to the nearest tick. Naive
    datetimes are taken to be in UTC.
    """

    wraps: Construct
    epoch: Epoch = "unix"
    unit: Unit | None = None

    def __post_init__(self):
        if isinstance(self.epoch, str) and self.epoch not in EPOCHS:
            raise PaboError(
                f"UNKNOWN EPOCH {self.epoch!r}. MUST BE ONE OF {list(EPOCHS)} OR A DATETIME."
            )
        if not isinstance(self.epoch, (str, datetime)):
            raise PaboError(
                f"THE EPOCH MUST BE A STR OR A DATETIME, GOT {self.epoch!r}."
            )
        if self.unit is not None and self.unit not in UNITS:
            raise PaboError(
                f"UNKNOWN UNIT {self.unit!r}. MUST BE ONE OF {list(UNITS)}."
            )

    def _origin(self) -> tuple[datetime, Fraction]:
        if isinstance(self.epoch, str):
            origin, unit = EPOCHS[self.epoch]
        else:
            origin, unit = self.epoch, "s"
        if origin.tzinfo is None:
            origin = origin.replace(tzinfo=timezone.utc)
        return origin, UNITS[self.unit or unit]

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        if not isinstance(data, datetime):
            raise ValidationError(f"EXPECTED A DATETIME, GOT {type(data).__name__}.")
        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)
        origin, unit = self._origin()
        delta = data - origin
        micro = (delta.days * 86400 + delta.seconds) * 10**6 + delta.microseconds
        exact = Fraction(micro) / unit
        ticks = (
            round(exact)
            if isinstance(self.wraps, (Int, VarInt, ZigZag))
            else float(exact)
        )
        self.wraps._build(ticks, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        origin, unit = self._origin()
        micro = Fraction(self.wraps._parse(stream, ctx)) * unit
        return origin + timedelta(microseconds=round(micro))
