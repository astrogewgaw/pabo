import enum
from datetime import datetime, timezone

import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


class Color(enum.Enum):
    """
    A plain enum for testing `pb.Enum`.
    """

    RED = 1
    GREEN = 2


class Perm(enum.IntFlag):
    """
    Unix-style permission bits for testing `pb.FlagsEnum`.
    """

    R = 4
    W = 2
    X = 1


def test_enum():
    """
    `Enum` parses to members and builds from a member, its value or its name, and raises
    `ValidationError` for an unknown value when parsing or unknown name when building.
    """

    c = pb.Enum(pb.Int(1), Color)
    assert c.parse(b"\x02") is Color.GREEN
    assert c.build(Color.RED) == b"\x01"
    assert c.build(2) == b"\x02"
    assert c.build("GREEN") == b"\x02"
    assert c.size == 1
    with pytest.raises(pb.ValidationError):
        c.parse(b"\x07")
    with pytest.raises(pb.ValidationError):
        c.build("BLUE")


def test_flags_enum():
    """
    `FlagsEnum` parses to a combination of flags and builds from combined flags or a
    plain integer.
    """

    c = pb.FlagsEnum(pb.Int(1), Perm)
    assert c.parse(b"\x06") == Perm.R | Perm.W
    assert c.build(Perm.R | Perm.X) == b"\x05"
    assert c.build(3) == b"\x03"
    assert c.size == 1


def test_unix_timestamp():
    """
    A Unix `Timestamp` stores seconds since 1970 and parses back to an aware UTC
    `datetime`, treating naive datetimes as UTC when building.
    """

    c = pb.Timestamp(pb.Int(4))
    moment = datetime(2020, 1, 1, tzinfo=timezone.utc)
    raw = c.build(moment)
    assert pb.Int(4).parse(raw) == 1577836800
    assert c.parse(raw) == moment
    assert c.build(datetime(2020, 1, 1)) == raw
    assert c.size == 4


def test_mjd_timestamp():
    """
    An MJD `Timestamp` over a `Float` stores fractional days since 1858-11-17
    (J2000 noon is 51544.5) and parses back to the same moment.
    """

    c = pb.Timestamp(pb.Float(8), epoch="mjd")
    moment = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    raw = c.build(moment)
    assert pb.Float(8).parse(raw) == 51544.5
    assert c.parse(raw) == moment


def test_custom_epoch_and_unit():
    """
    A `Timestamp` with a custom (naive, so UTC) epoch and millisecond unit stores ticks
    since that epoch and round-trips sub-second times.
    """

    c = pb.Timestamp(pb.Int(8), epoch=datetime(2000, 1, 1), unit="ms")
    moment = datetime(2000, 1, 1, 0, 0, 1, 500000, tzinfo=timezone.utc)
    assert pb.Int(8).parse(c.build(moment)) == 1500
    assert c.parse(c.build(moment)) == moment


@pytest.mark.parametrize(
    "unit, ticks", [("s", 1), ("ms", 1_000), ("us", 1_000_000), ("ns", 1_000_000_000)]
)
def test_unix_timestamp_units(unit, ticks):
    """
    A Unix `Timestamp` stores one second as the right number of ticks for each unit
    (s, ms, us, ns) and parses it back.
    """

    c = pb.Timestamp(pb.Int(8), unit=unit)
    moment = datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert pb.Int(8).parse(c.build(moment)) == ticks
    assert c.parse(c.build(moment)) == moment


def test_timestamp_errors():
    """
    `Timestamp` rejects an unknown epoch name or unit and a non-string unit at
    construction, and building a non-`datetime` raises `ValidationError`.
    """

    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Timestamp(pb.Int(4), epoch="martian")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Timestamp(pb.Int(4), unit="fortnight")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Timestamp(pb.Int(4), unit=1e-3)
    with pytest.raises(pb.ValidationError):
        pb.Timestamp(pb.Int(4)).build(5)


def test_timestamp_rounds_unless_wrapping_a_float():
    """
    `Timestamp` passes whole ticks to anything but a `Float` (here an `Adapted`
    that needs an int), and fractional ticks to a `Float`.
    """

    octal = pb.Adapted(
        pb.PaddedString(12, "ascii"), lambda t: int(t, 8), lambda v: f"{v:011o}"
    )
    c = pb.Timestamp(octal)
    moment = datetime(2023, 11, 14, 22, 13, 20, 600000, tzinfo=timezone.utc)
    assert c.build(moment) == b"14524770401\x00"
    assert c.parse(b"14524770400\x00") == moment.replace(microsecond=0)
    floats = pb.Timestamp(pb.f64)
    assert floats.parse(floats.build(moment)) == moment


def test_flagsenum_rejects_values_that_are_not_ints():
    """
    Building a `FlagsEnum` from something that is not an int raises a
    `ValidationError`.
    """

    class Mode(enum.IntFlag):
        """
        Two flags.
        """

        READ = 1
        WRITE = 2

    with pytest.raises(pb.ValidationError, match="NOT A VALUE OF Mode"):
        pb.FlagsEnum(pb.u8, Mode).build("read")
