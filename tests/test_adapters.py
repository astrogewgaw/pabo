import enum
from datetime import datetime, timezone

import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


class Color(enum.Enum):
    RED = 1
    GREEN = 2


class Perm(enum.IntFlag):
    R = 4
    W = 2
    X = 1


def test_enum():
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
    c = pb.FlagsEnum(pb.Int(1), Perm)
    assert c.parse(b"\x06") == Perm.R | Perm.W
    assert c.build(Perm.R | Perm.X) == b"\x05"
    assert c.build(3) == b"\x03"
    assert c.size == 1


def test_unix_timestamp():
    c = pb.Timestamp(pb.Int(4))
    moment = datetime(2020, 1, 1, tzinfo=timezone.utc)
    raw = c.build(moment)
    assert pb.Int(4).parse(raw) == 1577836800
    assert c.parse(raw) == moment
    assert c.build(datetime(2020, 1, 1)) == raw
    assert c.size == 4


def test_mjd_timestamp():
    c = pb.Timestamp(pb.Float(8), epoch="mjd")
    moment = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    raw = c.build(moment)
    assert pb.Float(8).parse(raw) == 51544.5
    assert c.parse(raw) == moment


def test_custom_epoch_and_unit():
    c = pb.Timestamp(pb.Int(8), epoch=datetime(2000, 1, 1), unit="ms")
    moment = datetime(2000, 1, 1, 0, 0, 1, 500000, tzinfo=timezone.utc)
    assert pb.Int(8).parse(c.build(moment)) == 1500
    assert c.parse(c.build(moment)) == moment


@pytest.mark.parametrize(
    "unit, ticks", [("s", 1), ("ms", 1_000), ("us", 1_000_000), ("ns", 1_000_000_000)]
)
def test_unix_timestamp_units(unit, ticks):
    c = pb.Timestamp(pb.Int(8), unit=unit)
    moment = datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)
    assert pb.Int(8).parse(c.build(moment)) == ticks
    assert c.parse(c.build(moment)) == moment


def test_timestamp_errors():
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Timestamp(pb.Int(4), epoch="martian")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Timestamp(pb.Int(4), unit="fortnight")
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Timestamp(pb.Int(4), unit=1e-3)
    with pytest.raises(pb.ValidationError):
        pb.Timestamp(pb.Int(4)).build(5)
