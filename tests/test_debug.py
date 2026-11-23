import io

import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


def test_probe_parsing():
    out = io.StringIO()
    spec = pb.Spec({"a": pb.u8, "probe": pb.Probe("here", file=out), "b": pb.u8})
    assert spec.parse(b"\x01\x02") == {"a": 1, "probe": None, "b": 2}
    text = out.getvalue()
    assert "Probe 'here' while parsing, at offset 1" in text
    assert "{'a': 1}" in text
    assert "00000001  02" in text
    assert spec.size == 2


def test_probe_building():
    out = io.StringIO()
    spec = pb.Spec({"a": pb.u8, "probe": pb.Probe(file=out)})
    assert spec.build({"a": 1}) == b"\x01"
    assert "while building, at offset 1" in out.getvalue()


def test_probe_rejects_non_streams():
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Probe(file="stderr")


def test_hexdump():
    from pabo.base import hexdump

    assert hexdump(b"AB\x00", 16) == "00000010  41 42 00" + " " * 39 + "  AB."
    assert len(hexdump(bytes(40)).splitlines()) == 3
