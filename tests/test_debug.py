import io

import pytest
from beartype.roar import BeartypeCallHintParamViolation

import pabo as pb


def test_probe_parsing():
    """
    A `Probe` in a specification prints its name, offset, the context so far and a hex
    dump of the following bytes while parsing, and takes up no space.
    """
    out = io.StringIO()
    spec = pb.Spec({"a": pb.u8, "probe": pb.Probe("here", file=out), "b": pb.u8})
    assert spec.parse(b"\x01\x02") == {"a": 1, "probe": None, "b": 2}
    text = out.getvalue()
    assert "Probe 'here' while parsing, at offset 1" in text
    assert "{'a': 1}" in text
    assert "00000001  02" in text
    assert spec.size == 2


def test_probe_building():
    """
    A `Probe` prints the offset while building and can be left out of the input.
    """
    out = io.StringIO()
    spec = pb.Spec({"a": pb.u8, "probe": pb.Probe(file=out)})
    assert spec.build({"a": 1}) == b"\x01"
    assert "while building, at offset 1" in out.getvalue()


def test_probe_rejects_non_streams():
    """
    `Probe` rejects a `file` that is not a stream (a string) with a `PaboError` or a
    beartype violation.
    """
    with pytest.raises((pb.PaboError, BeartypeCallHintParamViolation)):
        pb.Probe(file="stderr")


def test_debug_opens_the_debugger_where_parsing_fails(monkeypatch):
    """
    `Debug` starts `pdb.post_mortem` with the traceback of a failure, then raises
    the error again; it is transparent when nothing fails.
    """
    import pdb

    seen = []
    monkeypatch.setattr(pdb, "post_mortem", lambda tb: seen.append(tb))
    c = pb.Spec({"a": pb.u8, "b": pb.Debug(pb.u16)})
    assert c.parse(b"\x01\x02\x00") == {"a": 1, "b": 2}
    assert c.build({"a": 1, "b": 2}) == b"\x01\x02\x00"
    with pytest.raises(pb.StreamError):
        c.parse(b"\x01\x02")
    with pytest.raises(pb.ValidationError):
        c.build({"a": 1, "b": -1})
    assert len(seen) == 2 and all(tb is not None for tb in seen)
