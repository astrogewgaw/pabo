import pytest

import pabo as pb

PNG = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\x0d"
    + b"IHDR"
    + b"\x00\x00\x02\x5a"
    + b"\x00\x00\x00\xac"
)


@pytest.fixture
def png():
    """
    A specification for the start of a PNG file: signature, IHDR chunk size and tag, and
    the big-endian image width and height.
    """
    return pb.Spec(
        {
            "magic": pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8)),
            "ihdr_size": pb.Int(4, endian="big"),
            "ihdr_id": pb.Const(b"IHDR", pb.Bytes(4)),
            "width": pb.Int(4, endian="big"),
            "height": pb.Int(4, endian="big"),
        }
    )


def test_readme_example(png):
    """
    The README example: parsing a PNG header gives the expected field dict and the
    specification has a static `size`.
    """
    data = png.parse(PNG)
    assert data == {
        "magic": b"\x89PNG\r\n\x1a\n",
        "ihdr_size": 13,
        "ihdr_id": b"IHDR",
        "width": 602,
        "height": 172,
    }
    assert png.size == len(PNG)


def test_roundtrip(png):
    """
    Building the parsed PNG header gives back the original bytes.
    """
    assert png.build(png.parse(PNG)) == PNG


def test_parse_from_file(png, tmp_path):
    """
    `parse()` reads from a file given as a `Path` or a `str`.
    """
    path = tmp_path / "example.png"
    path.write_bytes(PNG)
    assert png.parse(path)["width"] == 602
    assert png.parse(str(path))["height"] == 172


def test_missing_field_raises(png):
    """
    Building with required fields missing from the input raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        png.build({"width": 1})


def test_nested():
    """
    A specification nested in another parses to a nested dict and round-trips.
    """
    inner = pb.Spec({"a": pb.Int(1), "b": pb.Int(1)})
    outer = pb.Spec({"x": inner, "y": pb.Int(2)})
    raw = b"\x01\x02\x03\x00"
    assert outer.parse(raw) == {"x": {"a": 1, "b": 2}, "y": 3}
    assert outer.build(outer.parse(raw)) == raw


def test_build_fills_in_constants(png):
    """
    `Const` fields can be left out when building and are filled in automatically.
    """
    data = {"ihdr_size": 13, "width": 602, "height": 172}
    assert png.build(data) == PNG


def test_build_with_padding():
    """
    `Padding` fields can be left out when building and are written as zero bytes.
    """
    c = pb.Spec({"a": pb.Int(1), "pad": pb.Padding(2), "b": pb.Int(1)})
    assert c.build({"a": 1, "b": 2}) == b"\x01\x00\x00\x02"


def test_nested_key_error_is_not_masked():
    """
    A field missing from a nested specification's input raises a `PaboError` that
    names the missing field (`'a'`).
    """
    inner = pb.Spec({"a": pb.Int(1)})
    outer = pb.Spec({"x": inner})
    with pytest.raises(pb.PaboError, match="'a'"):
        outer.build({"x": {}})


def test_dependent_fields():
    """
    Later fields can use earlier ones for their size or count, via `this.n` or a
    lambda, when both parsing and building.
    """
    spec = pb.Spec(
        {
            "n": pb.Int(1),
            "data": pb.Bytes(pb.this.n),
            "words": pb.Repeat(pb.Int(2), lambda ctx: ctx.n - 1),
        }
    )
    raw = b"\x03abc\x01\x00\x02\x00"
    data = spec.parse(raw)
    assert data == {"n": 3, "data": b"abc", "words": [1, 2]}
    assert spec.build(data) == raw


def test_reference_to_parent_field():
    """
    A nested specification can refer to a field of its parent via `this._.n`.
    """
    inner = pb.Spec({"data": pb.Bytes(pb.this._.n)})
    outer = pb.Spec({"n": pb.Int(1), "inner": inner})
    assert outer.parse(b"\x02ab") == {"n": 2, "inner": {"data": b"ab"}}
    assert outer.build({"n": 2, "inner": {"data": b"ab"}}) == b"\x02ab"


def test_build_requires_dict():
    """
    Building a specification from a non-mapping (a list) raises `PaboError`.
    """
    with pytest.raises(pb.PaboError):
        pb.Spec({"a": pb.Int(1)}).build([1])


def test_embedded():
    """
    `Embedded` merges a specification's fields into the enclosing one, so later fields
    can refer to them; it also parses on its own.
    """
    common = pb.Spec({"a": pb.Int(1), "b": pb.Int(1)})
    spec = pb.Spec({"x": pb.Int(1), "_": pb.Embedded(common), "c": pb.Bytes(pb.this.a)})
    raw = b"\x09\x02\x03ab"
    data = spec.parse(raw)
    assert data == {"x": 9, "a": 2, "b": 3, "c": b"ab"}
    assert spec.build(data) == raw
    assert spec.sizeof(data) == 5
    assert pb.Embedded(common).parse(b"\x01\x02") == {"a": 1, "b": 2}


def test_nested_specs_roundtrip_deeply():
    """
    Specifications nested several levels deep, including inside a `Sequential`, give
    attribute access at every level and round-trip.
    """
    spec = pb.Spec(
        {
            "a": pb.Spec(
                {
                    "b": pb.Spec({"c": pb.Int(2)}),
                    "d": pb.Seq([pb.Int(1), pb.Spec({"e": pb.Int(1)})]),
                }
            )
        }
    )
    raw = b"\x01\x00\x02\x03"
    data = spec.parse(raw)
    assert data.a.b.c == 1 and data.a.d[1].e == 3
    assert spec.build(data) == raw


def test_docs_in_errors():
    """
    An error in a documented field carries the field's `docs` and quotes it in the
    message.
    """
    spec = pb.Spec({"w": pb.Int(4) / "Image width"})
    with pytest.raises(pb.StreamError) as info:
        spec.parse(b"\x00")
    assert info.value.docs == "Image width"
    assert "'Image width'" in str(info.value)


def test_trace(capsys):
    """
    `parse(..., trace=True)` prints each field with its byte range and value plus a hex
    dump to stderr, indenting nested specifications.
    """
    spec = pb.Spec({"a": pb.Int(1), "inner": pb.Spec({"b": pb.Int(2)})})
    spec.parse(b"\x01\x02\x00", trace=True)
    err = capsys.readouterr().err
    assert "a [0:1] = 1" in err
    assert "  b [1:3] = 2" in err
    assert "00000001  02 00" in err


def test_trace_to_stream():
    """
    `parse(..., trace=stream)` writes the trace to the given stream.
    """
    import io

    out = io.StringIO()
    pb.Spec({"a": pb.Int(1)}).parse(b"\x07", trace=out)
    assert "a [0:1] = 7" in out.getvalue()


def test_describe():
    """
    `describe()` lists each field's offset, size, name, type and docs, indenting nested
    specifications and showing `?` for sizes or offsets that are not known statically.
    """
    spec = pb.Spec(
        {
            "magic": pb.Const(b"PB", pb.Bytes(2)) / "Magic number",
            "n": pb.u8,
            "hdr": pb.Spec({"w": pb.u16, "h": pb.u16}, endian="big"),
            "data": pb.Bytes(pb.this.n),
            "crc": pb.u32,
        }
    )
    lines = spec.describe().splitlines()
    assert lines[0].split() == ["offset", "size", "field", "type", "docs"]
    assert lines[1].split()[:3] == ["0", "2", "magic"] and lines[1].endswith(
        "Magic number"
    )
    assert lines[3].split()[:4] == ["3", "4", "hdr", "Specification(endian='big')"]
    assert lines[4].split()[:3] == ["3", "2", "w"]
    assert lines[6].split()[:3] == ["7", "?", "data"]
    assert lines[7].split()[:3] == ["?", "4", "crc"]
    assert pb.u16.describe().splitlines()[1].split()[:2] == ["0", "2"]


def test_compiled_plan_is_used_and_matches():
    """
    A fixed-size specification compiles to a single `struct` format, parses and builds
    the same as the slow path, and builds a `Flag` given as `1` or `True` as `1`.
    """
    spec = pb.Spec(
        {
            "magic": pb.Const(b"AB", pb.Bytes(2)),
            "a": pb.u16,
            "b": pb.i32,
            "c": pb.f64,
            "flag": pb.Flag(),
        },
        endian="big",
    )
    plan = spec._plan(pb.Context())
    assert plan is not None and plan.struct.format == ">2sHid?"
    raw = (
        b"AB" + b"\x00\x01" + b"\xff\xff\xff\xfe" + b"\x3f\xf8" + b"\x00" * 6 + b"\x02"
    )
    data = spec.parse(raw)
    assert data == {"magic": b"AB", "a": 1, "b": -2, "c": 1.5, "flag": True}
    assert spec.build(data) == raw[:-1] + b"\x01"
    assert spec.build({"a": 1, "b": -2, "c": 1.5, "flag": 1}) == raw[:-1] + b"\x01"


def test_compiled_plan_falls_back_for_detailed_errors():
    """
    When the compiled plan hits a bad constant, short read, out-of-range integer or
    wrong-length bytes, the error still names the failing field like the slow path.
    """
    spec = pb.Spec(
        {"magic": pb.Const(b"AB", pb.Bytes(2)), "a": pb.u16, "d": pb.Bytes(2)}
    )
    with pytest.raises(pb.ConstError) as info:
        spec.parse(b"XY\x00\x00ab")
    assert info.value.where == "magic"
    with pytest.raises(pb.StreamError) as info:
        spec.parse(b"AB\x00")
    assert info.value.where == "a"
    with pytest.raises(pb.ValidationError) as info:
        spec.build({"a": 70000, "d": b"ab"})
    assert info.value.where == "a"
    with pytest.raises(pb.ValidationError):
        spec.build({"a": 1, "d": b"abc"})
    with pytest.raises(pb.ConstError):
        spec.build({"magic": b"XY", "a": 1, "d": b"ab"})


def test_no_plan_for_mixed_or_dynamic_fields():
    """
    No compiled plan is made for mixed endianness, dynamic sizes or an empty
    specification.
    """
    assert pb.Spec({"a": pb.u16le, "b": pb.u16be})._plan(pb.Context()) is None
    assert pb.Spec({"n": pb.u8, "d": pb.Bytes(pb.this.n)})._plan(pb.Context()) is None
    assert pb.Spec({})._plan(pb.Context()) is None


# Real-world formats.


def test_wav_file(tmp_path):
    """
    A WAV file written by the `wave` module parses into the right format chunk and
    samples, and building from those values (with `Rebuild` sizes) gives the same bytes.
    """
    chunk = lambda tag, body: pb.Spec(
        {
            "id": pb.Const(tag, pb.Bytes(4)),
            "size": pb.Rebuild(
                pb.u32,
                lambda ctx: (
                    body.sizeof(ctx) if tag == b"fmt " else 2 * len(ctx.samples)
                ),
            ),
            "_": pb.Embedded(body),
        }
    )
    fmt = pb.Spec(
        {
            "audio_format": pb.u16,
            "channels": pb.u16,
            "rate": pb.u32,
            "byte_rate": pb.Rebuild(
                pb.u32, lambda ctx: ctx.rate * ctx.channels * ctx.bits // 8
            ),
            "block_align": pb.Rebuild(pb.u16, lambda ctx: ctx.channels * ctx.bits // 8),
            "bits": pb.u16,
        }
    )
    data = pb.Spec({"samples": pb.Array(pb.i16, count=lambda ctx: ctx.size // 2)})
    wav = pb.Spec(
        {
            "riff": pb.Const(b"RIFF", pb.Bytes(4)),
            "size": pb.Rebuild(
                pb.u32, lambda ctx: 4 + 24 + 8 + 2 * len(ctx.data.samples)
            ),
            "wave": pb.Const(b"WAVE", pb.Bytes(4)),
            "fmt": chunk(b"fmt ", fmt),
            "data": chunk(b"data", data),
            "end": pb.Terminated(),
        },
        endian="little",
    )
    import wave

    import numpy as np

    path = tmp_path / "tone.wav"
    samples = (np.sin(np.arange(100) / 5) * 1000).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(8000)
        f.writeframes(samples.tobytes())

    parsed = wav.parse(path)
    assert (
        parsed.fmt.channels == 1 and parsed.fmt.rate == 8000 and parsed.fmt.bits == 16
    )
    np.testing.assert_array_equal(parsed.data.samples, samples)
    built = wav.build(
        {
            "fmt": {"audio_format": 1, "channels": 1, "rate": 8000, "bits": 16},
            "data": {"samples": samples},
        }
    )
    assert built == path.read_bytes()


def _elfspec():
    """
    Return a specification for an ELF file header, switching endianness on the
    identification's data byte and address width on its class byte.
    """

    def body(endian):
        """
        Return the ELF header fields after the identification, in the given endianness.
        """
        word = lambda ctx: ctx._.ident.cls == 2
        addr = pb.If(word, pb.u64, pb.u32)
        return pb.Spec(
            {
                "type": pb.u16,
                "machine": pb.u16,
                "version": pb.u32,
                "entry": addr,
                "phoff": addr,
                "shoff": addr,
                "flags": pb.u32,
                "ehsize": pb.u16,
                "phentsize": pb.u16,
                "phnum": pb.u16,
                "shentsize": pb.u16,
                "shnum": pb.u16,
                "shstrndx": pb.u16,
            },
            endian=endian,
        )

    return pb.Spec(
        {
            "ident": pb.Spec(
                {
                    "magic": pb.Const(b"\x7fELF", pb.Bytes(4)),
                    "cls": pb.u8,
                    "data": pb.u8,
                    "version": pb.u8,
                    "osabi": pb.u8,
                    "abiversion": pb.u8,
                    "pad": pb.Padding(7),
                }
            ),
            "header": pb.Switch(
                lambda ctx: ctx.ident.data, {1: body("little"), 2: body("big")}
            ),
        }
    )


def test_elf_header_of_running_python():
    """
    The ELF header of the running Python executable parses with a valid class and
    data byte and the expected header size; skipped when it is not an ELF binary.
    """
    import sys

    if not sys.executable:
        pytest.skip("No Python executable.")
    with open(sys.executable, "rb") as f:
        if f.read(4) != b"\x7fELF":
            pytest.skip("Not running from an ELF binary.")
    elf = _elfspec()
    data = elf.parse(sys.executable)
    assert data.ident.cls in (1, 2) and data.ident.data in (1, 2)
    assert data.header.ehsize == (64 if data.ident.cls == 2 else 52)


def test_elf_header_both_endians():
    """
    A 64-bit ELF header built in little and big endian is 64 bytes and parses back to
    the same values; a 32-bit one is 52 bytes.
    """
    elf = _elfspec()
    values = {
        "type": 2,
        "machine": 62,
        "version": 1,
        "entry": 0x401000,
        "phoff": 64,
        "shoff": 4096,
        "flags": 0,
        "ehsize": 64,
        "phentsize": 56,
        "phnum": 2,
        "shentsize": 64,
        "shnum": 5,
        "shstrndx": 4,
    }
    for data_byte in (1, 2):
        ident = {"cls": 2, "data": data_byte, "version": 1, "osabi": 0, "abiversion": 0}
        raw = elf.build({"ident": ident, "header": values})
        assert len(raw) == 64
        assert elf.parse(raw).header == values
    ident32 = {"cls": 1, "data": 1, "version": 1, "osabi": 0, "abiversion": 0}
    assert len(elf.build({"ident": ident32, "header": {**values, "ehsize": 52}})) == 52


def test_sigproc_filterbank_header():
    """
    A SIGPROC filterbank file: a keyword header built with `RepeatUntil` and `Switch`,
    read back into a metadata dict, followed by 2-bit packed data sized from `nchans`.
    """
    key = pb.PascalString(pb.i32)
    values = {
        "telescope_id": pb.i32,
        "machine_id": pb.i32,
        "data_type": pb.i32,
        "nchans": pb.i32,
        "nbits": pb.i32,
        "nifs": pb.i32,
        "tsamp": pb.f64,
        "tstart": pb.f64,
        "fch1": pb.f64,
        "foff": pb.f64,
        "source_name": pb.PascalString(pb.i32),
        "HEADER_END": pb.Computed(None),
    }
    entry = pb.Spec({"key": key, "value": pb.Switch(pb.this.key, values)})
    header = pb.Spec(
        {
            "start": pb.Const("HEADER_START", key),
            "entries": pb.RepeatUntil(lambda e, ctx: e.key == "HEADER_END", entry),
        },
        endian="little",
    )
    filterbank = pb.Spec(
        {
            "header": header,
            "meta": pb.Computed(
                lambda ctx: {e.key: e.value for e in ctx.header.entries}
            ),
            "data": pb.Array(
                pb.u8,
                count=lambda ctx: ctx.meta["nchans"] * 2,
                packing=2,
                bitorder="little",
            ),
        }
    )
    entries = [
        {"key": "source_name", "value": "J0437-4715"},
        {"key": "telescope_id", "value": 4},
        {"key": "nchans", "value": 8},
        {"key": "nbits", "value": 2},
        {"key": "tsamp", "value": 6.4e-5},
        {"key": "fch1", "value": 1500.0},
        {"key": "foff", "value": -0.5},
        {"key": "HEADER_END", "value": None},
    ]
    raw_header = header.build({"entries": entries})
    assert raw_header.startswith(b"\x0c\x00\x00\x00HEADER_START")
    assert raw_header.endswith(b"\x0a\x00\x00\x00HEADER_END")
    samples = [i % 4 for i in range(16)]
    raw = raw_header + pb.Array(pb.u8, count=16, packing=2, bitorder="little").build(
        samples
    )
    data = filterbank.parse(raw)
    assert data.meta["source_name"] == "J0437-4715"
    assert data.meta["tsamp"] == 6.4e-5 and data.meta["nchans"] == 8
    assert list(data.data) == samples
