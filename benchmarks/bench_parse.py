"""
Benchmarks of pabo against struct and other binary parsing libraries.

Run with:

    pip install -e ".[bench]"
    pytest benchmarks/ --benchmark-group-by=group

Three cases are timed, each parsed into the library's usual result:

- header: a PNG header (5 fields, 24 bytes, two of them constants);
- records: 1,000 records of (u16, u32, f32);
- array: 1,000,000 float32 values.

Libraries that are not installed are skipped, as are cases a library cannot
express. duckparse is only on GitHub (`pip install git+https://github.com/i64/duckparse`),
and pystructs 0.4 needs Python 3.13, so neither is in the `bench` extra.
"""

import collections
import collections.abc
import struct
import sys
import types
from io import BytesIO
from pathlib import Path

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
MAGIC = b"\x89PNG\r\n\x1a\n"
COUNT = 1_000_000
ARRAY = np.arange(COUNT, dtype="<f4").tobytes()
RECORDS = b"".join(struct.pack("<HIf", i % 65536, i, i / 2) for i in range(1000))

# CASES[group][implementation] = (parse, slow): `parse` takes no arguments and
# returns its result; `slow` cases (seconds per call) are timed in a few rounds.
CASES: dict[str, dict[str, tuple]] = {"header": {}, "records": {}, "array": {}}
# Implementations whose library is not installed, with the reason.
MISSING: dict[str, str] = {}


def case(group, name, slow=False):
    """
    Register a function as the `name` implementation of `group`.
    """

    def register(func):
        CASES[group][name] = (func, slow)
        return func

    return register


# pabo

png = pb.Spec(
    {
        "magic": pb.Const(MAGIC, pb.Bytes(8)),
        "ihdr_size": pb.u32,
        "ihdr_id": pb.Const(b"IHDR", pb.Bytes(4)),
        "width": pb.u32,
        "height": pb.u32,
    },
    endian="big",
)
records = pb.Repeat(pb.Spec({"a": pb.u16, "b": pb.u32, "c": pb.f32}), 1000)
array = pb.Array(pb.f32le, count=COUNT)
case("header", "pabo")(lambda: png.parse(HEADER))
case("records", "pabo")(lambda: records.parse(RECORDS))
case("array", "pabo")(lambda: array.parse(ARRAY))


# struct, from the standard library: the floor for header and records, since it
# skips everything a library adds (checking constants, naming fields, ...).

HEADER_STRUCT = struct.Struct(">8sI4sII")
RECORD_STRUCT = struct.Struct("<HIf")
case("header", "struct")(lambda: HEADER_STRUCT.unpack(HEADER))
case("records", "struct")(lambda: list(RECORD_STRUCT.iter_unpack(RECORDS)))
case("array", "struct")(lambda: struct.unpack(f"<{COUNT}f", ARRAY))


# construct, plain and compiled

try:
    import construct as cs
except ImportError:
    MISSING["construct"] = "construct is not installed"
else:
    cs_png = cs.Struct(
        "magic" / cs.Const(MAGIC),
        "ihdr_size" / cs.Int32ub,
        "ihdr_id" / cs.Const(b"IHDR"),
        "width" / cs.Int32ub,
        "height" / cs.Int32ub,
    )
    cs_records = cs.Array(
        1000, cs.Struct("a" / cs.Int16ul, "b" / cs.Int32ul, "c" / cs.Float32l)
    )
    cs_array = cs.Array(COUNT, cs.Float32l)
    for suffix, compile in (("", lambda c: c), ("_compiled", lambda c: c.compile())):
        for group, construct, data, slow in (
            ("header", cs_png, HEADER, False),
            ("records", cs_records, RECORDS, False),
            ("array", cs_array, ARRAY, True),
        ):
            parser = compile(construct)
            case(group, "construct" + suffix, slow)(
                lambda parser=parser, data=data: parser.parse(data)
            )


# dissect.cstruct: C declarations, compiled to Python (no constants: the magic is
# checked by hand)

try:
    from dissect.cstruct import cstruct
except ImportError:
    MISSING["dissect"] = "dissect.cstruct is not installed"
else:
    dissect_be = cstruct(endian=">").load(
        "struct png { char magic[8]; uint32 ihdr_size; char ihdr_id[4];"
        " uint32 width; uint32 height; };"
    )
    dissect_le = cstruct(endian="<").load(
        "struct record { uint16 a; uint32 b; float c; };"
    )
    dissect_records = dissect_le.record[1000]
    dissect_array = dissect_le.float[COUNT]

    @case("header", "dissect")
    def dissect_header():
        """
        Parse the header, and check its constants as the other libraries do.
        """

        header = dissect_be.png(HEADER)
        if header.magic != MAGIC or header.ihdr_id != b"IHDR":
            raise ValueError("bad PNG header")
        return header

    case("records", "dissect")(lambda: dissect_records(RECORDS))
    case("array", "dissect", slow=True)(lambda: dissect_array(ARRAY))


# Kaitai Struct: parsers generated from the .ksy files in benchmarks/kaitai/ by
# kaitai-struct-compiler 0.11 (`ksc -t python *.ksy`), for the kaitaistruct runtime.

try:
    import kaitaistruct  # noqa: F401
except ImportError:
    MISSING["kaitai"] = "kaitaistruct is not installed"
else:
    sys.path.insert(0, str(Path(__file__).parent / "kaitai"))
    from floats import Floats
    from png_header import PngHeader
    from records import Records

    sys.path.pop(0)
    case("header", "kaitai")(lambda: PngHeader.from_bytes(HEADER))
    case("records", "kaitai")(lambda: Records.from_bytes(RECORDS).items)
    case("array", "kaitai", slow=True)(lambda: Floats.from_bytes(ARRAY).values)


# bitstruct: bit-level format strings, in C. Little-endian data has to be
# byte-swapped first, since "<" in bitstruct reverses bits, not bytes.

try:
    import bitstruct.c as bitstruct
except ImportError:
    MISSING["bitstruct"] = "bitstruct is not installed"
else:
    bitstruct_png = bitstruct.CompiledFormatDict(
        "r64u32r32u32u32", ["magic", "ihdr_size", "ihdr_id", "width", "height"]
    )
    bitstruct_record = bitstruct.compile("u16u32f32")
    bitstruct_array = bitstruct.compile("f32" * COUNT)

    @case("header", "bitstruct")
    def bitstruct_header():
        """
        Parse the header, and check its constants as the other libraries do.
        """

        header = bitstruct_png.unpack(HEADER)
        if header["magic"] != MAGIC or header["ihdr_id"] != b"IHDR":
            raise ValueError("bad PNG header")
        return header

    @case("records", "bitstruct")
    def bitstruct_records():
        """
        Byte-swap the little-endian records, then unpack each (offsets in bits).
        """

        swapped = bitstruct.byteswap("244" * 1000, RECORDS)
        return [bitstruct_record.unpack_from(swapped, 80 * i) for i in range(1000)]

    case("array", "bitstruct", slow=True)(
        lambda: bitstruct_array.unpack(bitstruct.byteswap("4" * COUNT, ARRAY))
    )


# structures: unmaintained since 2018, and needs `collections.Sequence`, which
# Python 3.10 removed.

collections.Sequence = collections.abc.Sequence  # type: ignore[attr-defined]
try:
    import structures as st
except ImportError:
    MISSING["structures"] = "structures is not installed"
else:

    class StPNG(st.Struct):
        """
        The PNG header, for structures.
        """

        magic = st.Const(st.Bytes(8), MAGIC)
        ihdr_size = st.Integer(4, "big")
        ihdr_id = st.Const(st.Bytes(4), b"IHDR")
        width = st.Integer(4, "big")
        height = st.Integer(4, "big")

    class StRecord(st.Struct):
        """
        One record, for structures.
        """

        a = st.Integer(2, "little")
        b = st.Integer(4, "little")
        c = st.Float(4, "little")

    st_png = StPNG()
    st_records = st.RepeatExactly(StRecord(), 1000)
    st_array = st.RepeatExactly(st.Float(4, "little"), COUNT)
    case("header", "structures")(lambda: st_png.parse(HEADER))
    case("records", "structures")(lambda: st_records.parse(RECORDS))
    case("array", "structures", slow=True)(lambda: st_array.parse(ARRAY))


# bread: archived since 2018. On Python 3.12 its vendored `six` needs a stand-in,
# and it needs bitstring < 5. It has no floats (one is defined below) and no
# constants, so the header's constants are checked by hand.

sys.modules.setdefault("bread.vendor.six.moves", types.SimpleNamespace(range=range))
try:
    import bread
    from bitstring import BitArray
    from bread.field import BreadField
except ImportError:
    MISSING["bread"] = "bread (with bitstring < 5) is not installed"
else:

    def float32le(parent, **options):
        """
        A little-endian float32 field, which bread does not have.
        """

        return BreadField(
            32,
            lambda value: BitArray(floatle=value, length=32),
            lambda bits: bits.floatle,
            str_format=None,
        )

    bread_png = [
        {"endianness": bread.BIG_ENDIAN},
        ("magic", bread.string(8, encoding="latin-1")),
        ("ihdr_size", bread.uint32),
        ("ihdr_id", bread.string(4, encoding="latin-1")),
        ("width", bread.uint32),
        ("height", bread.uint32),
    ]
    bread_records = [
        {"endianness": bread.LITTLE_ENDIAN},
        (
            "items",
            bread.array(
                1000, [("a", bread.uint16), ("b", bread.uint32), ("c", float32le)]
            ),
        ),
    ]
    bread_array = [
        {"endianness": bread.LITTLE_ENDIAN},
        ("values", bread.array(COUNT, float32le)),
    ]

    @case("header", "bread")
    def bread_header():
        """
        Parse the header (bread decodes lazily, so convert it all), and check its
        constants as the other libraries do.
        """

        header = bread.parse(HEADER, bread_png).as_native()
        if header["magic"] != MAGIC.decode("latin-1") or header["ihdr_id"] != "IHDR":
            raise ValueError("bad PNG header")
        return header

    case("records", "bread", slow=True)(
        lambda: bread.parse(RECORDS, bread_records).as_native()["items"]
    )
    case("array", "bread", slow=True)(
        lambda: bread.parse(ARRAY, bread_array).as_native()["values"]
    )


# binmap: dataclasses mapped onto one struct format, so only the header (there are
# no repeats or arrays).

try:
    from binmap import BinmapDataclass, constant
    from binmap.types import unsignedinteger, unsignedlonglong
except ImportError:
    MISSING["binmap"] = "binmap is not installed"
else:

    class BinmapPNG(BinmapDataclass, byteorder=">"):
        """
        The PNG header, for binmap (constants as integers: it has no byte constants).
        """

        magic: unsignedlonglong = constant(int.from_bytes(MAGIC, "big"))
        ihdr_size: unsignedinteger = 0
        ihdr_id: unsignedinteger = constant(int.from_bytes(b"IHDR", "big"))
        width: unsignedinteger = 0
        height: unsignedinteger = 0

    case("header", "binmap")(lambda: BinmapPNG(HEADER))


# duckparse: parse-only, from GitHub. `@stream` classes read in the machine's byte
# order (little-endian here), and `@section` ones take a reader with an endianness.

try:
    from duckparse import section
    from duckparse import stream as duckstream
    from duckparse.btypes import F32, U16, U32, Contents, RepeatN
    from duckparse.reader import Reader
except ImportError:
    MISSING["duckparse"] = "duckparse is not installed"
else:

    @section
    class DuckPNG:
        """
        The PNG header, for duckparse.
        """

        magic: Contents[MAGIC]
        ihdr_size: U32
        ihdr_id: Contents[b"IHDR"]
        width: U32
        height: U32

    @section
    class DuckRecord:
        """
        One record, for duckparse.
        """

        a: U16
        b: U32
        c: F32

    @duckstream
    class DuckRecords:
        """
        1,000 records (the count is a string of code, run by duckparse).
        """

        items: RepeatN[DuckRecord, "range(1000)"]

    @duckstream
    class DuckFloats:
        """
        1,000,000 float32 values.
        """

        values: RepeatN[F32, f"range({COUNT})"]

    case("header", "duckparse")(
        lambda: DuckPNG(Reader(BytesIO(HEADER), endianness="big"))
    )
    case("records", "duckparse")(lambda: DuckRecords(BytesIO(RECORDS)).items)
    case("array", "duckparse", slow=True)(lambda: DuckFloats(BytesIO(ARRAY)).values)


# pystructs 0.4 (0.3 and earlier have no floats or arrays).

try:
    import pystructs as ps

    ps.Float32  # noqa: B018
except (ImportError, AttributeError):
    MISSING["pystructs"] = "pystructs 0.4 (Python 3.13+) is not installed"
else:

    class PsPNG(ps.Struct):
        """
        The PNG header, for pystructs (constants are checked by `validate()`).
        """

        class Meta:
            """
            Big-endian.
            """

            endian = "big"

        magic = ps.FixedBytes(8, default=MAGIC, validators=[ps.BytePattern(MAGIC)])
        ihdr_size = ps.UInt32()
        ihdr_id = ps.FixedBytes(
            4, default=b"IHDR", validators=[ps.BytePattern(b"IHDR")]
        )
        width = ps.UInt32()
        height = ps.UInt32()

    class PsRecord(ps.Struct):
        """
        One record, for pystructs.
        """

        class Meta:
            """
            Little-endian.
            """

            endian = "little"

        a = ps.UInt16()
        b = ps.UInt32()
        c = ps.Float32()

    class PsRecords(ps.Struct):
        """
        1,000 records.
        """

        items = ps.Array(ps.EmbeddedStruct(PsRecord), count=1000)

    class PsFloats(ps.Struct):
        """
        1,000,000 float32 values.
        """

        class Meta:
            """
            Little-endian.
            """

            endian = "little"

        values = ps.Array(ps.Float32(), count=COUNT)

    case("header", "pystructs")(lambda: PsPNG.parse(HEADER).validate())
    case("records", "pystructs")(lambda: PsRecords.parse(RECORDS).items)
    case("array", "pystructs", slow=True)(lambda: PsFloats.parse(ARRAY).values)


# dataclasses-struct: dataclasses compiled to one struct format each, so no
# constants (checked by hand) and no repeats (records are left out); a fixed-length
# list stands in for the array.

try:
    from typing import Annotated

    import dataclasses_struct as dcs
except ImportError:
    MISSING["dataclasses_struct"] = "dataclasses-struct is not installed"
else:

    @dcs.dataclass_struct(size="std", byteorder="big")
    class DcsPNG:
        """
        The PNG header, for dataclasses-struct.
        """

        magic: Annotated[bytes, 8]
        ihdr_size: dcs.U32
        ihdr_id: Annotated[bytes, 4]
        width: dcs.U32
        height: dcs.U32

    @dcs.dataclass_struct(size="std", byteorder="little")
    class DcsFloats:
        """
        1,000,000 float32 values.
        """

        values: Annotated[list[dcs.F32], COUNT]

    @case("header", "dataclasses_struct")
    def dcs_header():
        """
        Parse the header, and check its constants as the other libraries do.
        """

        header = DcsPNG.from_packed(HEADER)
        if header.magic != MAGIC or header.ihdr_id != b"IHDR":
            raise ValueError("bad PNG header")
        return header

    case("array", "dataclasses_struct", slow=True)(
        lambda: DcsFloats.from_packed(ARRAY).values
    )


def _params():
    """
    One test parameter per (group, implementation), plus skipped ones for the
    libraries that are not installed.
    """

    params = [
        pytest.param(group, name, id=f"{group}-{name}")
        for group, impls in CASES.items()
        for name in impls
    ]
    params += [
        pytest.param(None, name, id=name, marks=pytest.mark.skip(reason=reason))
        for name, reason in MISSING.items()
    ]
    return params


def _check(group, result):
    """
    Check that a result has the expected size and values, whatever its type.
    """

    if group == "header":
        values = result if isinstance(result, (tuple, list)) else None
        width = (
            values[3]
            if values
            else (result["width"] if isinstance(result, dict) else result.width)
        )
        assert width == 602
    elif group == "records":
        assert len(result) == 1000
        last = result[999]
        b = (
            last[1]
            if isinstance(last, tuple)
            else (last["b"] if isinstance(last, dict) else last.b)
        )
        assert b == 999
    else:
        assert len(result) == COUNT and result[-1] == COUNT - 1


@pytest.mark.parametrize("group, name", _params())
def test_parse(benchmark, group, name):
    """
    Time one implementation of one case.
    """

    parse, slow = CASES[group][name]
    benchmark.group = group
    benchmark.extra_info["implementation"] = name
    if slow:
        result = benchmark.pedantic(parse, rounds=3, iterations=1)
    else:
        result = benchmark(parse)
    _check(group, result)
