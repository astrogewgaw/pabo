"""
Benchmarks of pabo against struct, numpy and construct.

Run with:

    pip install pytest-benchmark construct
    pytest benchmarks/ --benchmark-group-by=group

construct is optional; its benchmarks are skipped if it is not installed.
"""

import struct

import numpy as np
import pytest

import pabo as pb

HEADER = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\x0d"
    + b"IHDR"
    + b"\x00\x00\x02\x5a"
    + b"\x00\x00\x00\xac"
)
ARRAY = np.arange(1_000_000, dtype="<f4").tobytes()
RECORDS = b"".join(struct.pack("<HIf", i % 65536, i, i / 2) for i in range(1000))

png = pb.Spec(
    {
        "magic": pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8)),
        "ihdr_size": pb.u32,
        "ihdr_id": pb.Const(b"IHDR", pb.Bytes(4)),
        "width": pb.u32,
        "height": pb.u32,
    },
    endian="big",
)
record = pb.Spec({"a": pb.u16, "b": pb.u32, "c": pb.f32})
records = pb.Repeat(record, 1000)
array = pb.Array(pb.Float(4), count=1_000_000)

try:
    import construct as cs
except ImportError:  # pragma: no cover
    cs = None

needs_construct = pytest.mark.skipif(cs is None, reason="construct is not installed")


@pytest.mark.benchmark(group="header")
def test_header_pabo(benchmark):
    assert benchmark(png.parse, HEADER)["width"] == 602


@pytest.mark.benchmark(group="header")
def test_header_struct(benchmark):
    fmt = struct.Struct(">8sI4sII")
    assert benchmark(fmt.unpack, HEADER)[3] == 602


@needs_construct
@pytest.mark.benchmark(group="header")
def test_header_construct(benchmark):
    c = cs.Struct(
        "magic" / cs.Const(b"\x89PNG\r\n\x1a\n"),
        "ihdr_size" / cs.Int32ub,
        "ihdr_id" / cs.Const(b"IHDR"),
        "width" / cs.Int32ub,
        "height" / cs.Int32ub,
    )
    assert benchmark(c.parse, HEADER).width == 602


@needs_construct
@pytest.mark.benchmark(group="header")
def test_header_construct_compiled(benchmark):
    c = cs.Struct(
        "magic" / cs.Const(b"\x89PNG\r\n\x1a\n"),
        "ihdr_size" / cs.Int32ub,
        "ihdr_id" / cs.Const(b"IHDR"),
        "width" / cs.Int32ub,
        "height" / cs.Int32ub,
    ).compile()
    assert benchmark(c.parse, HEADER).width == 602


@pytest.mark.benchmark(group="records")
def test_records_pabo(benchmark):
    assert len(benchmark(records.parse, RECORDS)) == 1000


@pytest.mark.benchmark(group="records")
def test_records_numpy(benchmark):
    dtype = np.dtype([("a", "<u2"), ("b", "<u4"), ("c", "<f4")])
    assert len(benchmark(np.frombuffer, RECORDS, dtype)) == 1000


@needs_construct
@pytest.mark.benchmark(group="records")
def test_records_construct(benchmark):
    c = cs.Array(1000, cs.Struct("a" / cs.Int16ul, "b" / cs.Int32ul, "c" / cs.Float32l))
    assert len(benchmark(c.parse, RECORDS)) == 1000


@pytest.mark.benchmark(group="array")
def test_array_pabo(benchmark):
    assert benchmark(array.parse, ARRAY).size == 1_000_000


@pytest.mark.benchmark(group="array")
def test_array_numpy(benchmark):
    assert benchmark(np.frombuffer, ARRAY, "<f4").size == 1_000_000


@needs_construct
@pytest.mark.benchmark(group="array")
def test_array_construct(benchmark):
    c = cs.Array(1_000_000, cs.Float32l)
    benchmark.pedantic(c.parse, (ARRAY,), rounds=1, iterations=1)
