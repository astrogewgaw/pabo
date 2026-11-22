"""
Adapters that turn raw values into richer Python objects.
"""

import enum
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any

from pabo.base import Construct
from pabo.errors import PaboError, ValidationError
from pabo.numeric import Int, VarInt, ZigZag

EPOCHS = {
    "unix": (datetime(1970, 1, 1, tzinfo=timezone.utc), 1.0),
    "mjd": (datetime(1858, 11, 17, tzinfo=timezone.utc), 86400.0),
}


@dataclass
class Enum(Construct):
    """
    Map the integers parsed by `wraps` to members of an `enum.Enum`.

    Parsing a value that is not a member raises a `ValidationError`. Building
    accepts a member, its value, or its name.
    """

    wraps: Construct
    enum: type[enum.Enum]

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _member(self, data) -> enum.Enum:
        try:
            if isinstance(data, str) and not isinstance(data, self.enum):
                return self.enum[data]
            return self.enum(data)
        except (KeyError, ValueError):
            raise ValidationError(
                f"{data!r} is not a member of {self.enum.__name__}."
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
    flags: type[enum.IntFlag]

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

    `epoch` is "unix" (seconds since 1970-01-01), "mjd" (Modified Julian Date:
    days since 1858-11-17) or a datetime. `unit` is the length of one tick in
    seconds; it defaults to 1 for "unix" and to 86400 for "mjd". When building
    into an integer, the value is rounded to the nearest tick. Naive datetimes
    are taken to be in UTC.
    """

    wraps: Construct
    epoch: Any = "unix"
    unit: float | None = None

    def __post_init__(self):
        if isinstance(self.epoch, str) and self.epoch not in EPOCHS:
            raise PaboError(
                f"Unknown epoch {self.epoch!r}. Must be one of {list(EPOCHS)} or a datetime."
            )
        if not isinstance(self.epoch, (str, datetime)):
            raise PaboError(f"The epoch must be a str or a datetime, got {self.epoch!r}.")

    def _origin(self) -> tuple[datetime, float]:
        if isinstance(self.epoch, str):
            origin, unit = EPOCHS[self.epoch]
        else:
            origin, unit = self.epoch, 1.0
        if origin.tzinfo is None:
            origin = origin.replace(tzinfo=timezone.utc)
        return origin, self.unit if self.unit is not None else unit

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _build(self, data, stream, ctx):
        if not isinstance(data, datetime):
            raise ValidationError(f"Expected a datetime, got {type(data).__name__}.")
        if data.tzinfo is None:
            data = data.replace(tzinfo=timezone.utc)
        origin, unit = self._origin()
        ticks = (data - origin) / timedelta(seconds=unit)
        if isinstance(self.wraps, (Int, VarInt, ZigZag)):
            ticks = round(ticks)
        self.wraps._build(ticks, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        origin, unit = self._origin()
        return origin + timedelta(seconds=self.wraps._parse(stream, ctx) * unit)
