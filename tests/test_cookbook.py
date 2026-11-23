"""
The real-world formats in the cookbook (docs/source/cookbook.md), parsed and built
against files written by the standard library and numpy, or by hand.
"""

import pytest

import pabo as pb


def test_png_header():
    """
    The header of a PNG file (signature and IHDR chunk) parses into its width and
    height, and builds back to the same bytes with the constants left out.
    """
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
    raw = b"\x89PNG\r\n\x1a\n" + bytes.fromhex("0000000d") + b"IHDR"
    raw += bytes.fromhex("0000025a000000ac")
    data = png.parse(raw)
    assert (data.width, data.height) == (602, 172)
    assert png.build({"ihdr_size": 13, "width": 602, "height": 172}) == raw


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


def test_ipv4_header():
    """
    A real IPv4 header (with a valid checksum) parses into its bit fields and
    addresses, builds back to the same bytes, and options are sized from `ihl`.
    """
    this = pb.this
    ipv4 = pb.Spec(
        {
            "vihl": pb.BitStruct({"version": pb.BitInt(4), "ihl": pb.BitInt(4)}),
            "tos": pb.u8,
            "length": pb.u16,
            "id": pb.u16,
            "frag": pb.BitStruct(
                {
                    "reserved": pb.BitPadding(1),
                    "dont_fragment": pb.BitFlag(),
                    "more_fragments": pb.BitFlag(),
                    "offset": pb.BitInt(13),
                }
            ),
            "ttl": pb.u8,
            "protocol": pb.u8,
            "checksum": pb.u16,
            "source": pb.Bytes(4),
            "destination": pb.Bytes(4),
            "options": pb.Bytes((this.vihl.ihl - 5) * 4),
        },
        endian="big",
    )
    raw = bytes.fromhex("450000730000400040" + "11b861c0a80001c0a800c7")
    data = ipv4.parse(raw)
    assert data.vihl == {"version": 4, "ihl": 5} and data.length == 0x73
    assert data.frag.dont_fragment and not data.frag.more_fragments
    assert data.ttl == 64 and data.protocol == 17 and data.options == b""
    assert ".".join(map(str, data.source)) == "192.168.0.1"
    assert ipv4.build(data) == raw
    # The header checksum: the ones' complement sum of all 16-bit words is 0xffff.
    words = pb.Repeat(pb.u16be, 10).parse(raw)
    total = sum(words)
    assert (total & 0xFFFF) + (total >> 16) == 0xFFFF
    # With options, `ihl` grows and the options are read too.
    withopts = bytes([0x46]) + raw[1:] + b"\x01\x01\x01\x00"
    assert ipv4.parse(withopts).options == b"\x01\x01\x01\x00"


def test_gzip_header():
    """
    The header of a file written by `gzip` parses into its flags, modification time
    and file name; the rest is raw deflate data and a CRC-32/size trailer.
    """
    import gzip
    import zlib
    from datetime import datetime, timezone
    from io import BytesIO

    this = pb.this
    header = pb.Spec(
        {
            "magic": pb.Const(b"\x1f\x8b", pb.Bytes(2)),
            "method": pb.Const(8, pb.u8),
            "flags": pb.u8,
            "mtime": pb.Timestamp(pb.u32),
            "xfl": pb.u8,
            "os": pb.u8,
            "extra": pb.If(this.flags & 4, pb.Prefixed(pb.u16, pb.GreedyBytes())),
            "name": pb.If(this.flags & 8, pb.CString("latin-1")),
            "comment": pb.If(this.flags & 16, pb.CString("latin-1")),
            "hcrc": pb.If(this.flags & 2, pb.u16),
        },
        endian="little",
    )
    gz = pb.Spec({"header": header, "rest": pb.GreedyBytes()})
    trailer = pb.Spec({"crc32": pb.u32, "size": pb.u32}, endian="little")

    text = b"hello world " * 10
    buffer = BytesIO()
    with gzip.GzipFile("hello.txt", "wb", fileobj=buffer, mtime=1700000000) as f:
        f.write(text)
    raw = buffer.getvalue()

    data = gz.parse(raw)
    assert data.header.flags == 8 and data.header.name == "hello.txt"
    assert data.header.mtime == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert data.header.extra is None and data.header.comment is None
    assert zlib.decompress(data.rest[:-8], -15) == text
    assert trailer.parse(data.rest[-8:]) == {"crc32": zlib.crc32(text), "size": 120}
    assert header.build(data.header) + data.rest == raw


def _zipentry():
    """
    A ZIP local file entry: a header, the file name and the (compressed) data.
    """
    from datetime import datetime
    from enum import IntEnum

    this = pb.this

    class Method(IntEnum):
        """
        ZIP compression methods.
        """

        STORED = 0
        DEFLATED = 8

    def dostime(v):
        return datetime(
            1980 + (v >> 25),
            (v >> 21) & 15,
            (v >> 16) & 31,
            (v >> 11) & 31,
            (v >> 5) & 63,
            (v & 31) * 2,
        )

    def fromdatetime(d):
        return (
            (d.year - 1980) << 25
            | d.month << 21
            | d.day << 16
            | d.hour << 11
            | d.minute << 5
            | d.second // 2
        )

    return pb.Spec(
        {
            "signature": pb.Const(b"PK\x03\x04", pb.Bytes(4)),
            "version": pb.u16,
            "flags": pb.u16,
            "method": pb.Enum(pb.u16, Method),
            "modified": pb.Adapted(pb.u32, dostime, fromdatetime),
            "crc32": pb.u32,
            "csize": pb.Rebuild(pb.u32, pb.lenof(this.data)),
            "usize": pb.u32,
            "namelen": pb.Rebuild(pb.u16, pb.lenof(this.name)),
            "extralen": pb.Rebuild(pb.u16, pb.lenof(this.extra)),
            "name": pb.PaddedString(this.namelen),
            "extra": pb.Bytes(this.extralen),
            "data": pb.Bytes(this.csize),
        },
        endian="little",
    )


def test_zip_entries():
    """
    The entries of a ZIP archive written by `zipfile` (one stored, one deflated) parse
    with their names, times, CRCs and data, `Greedy` stopping at the central
    directory, and each entry builds back to the same bytes.
    """
    import zipfile
    import zlib
    from datetime import datetime
    from io import BytesIO

    entry = _zipentry()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("a.txt", (2024, 5, 6, 7, 8, 10)), b"alpha")
        info = zipfile.ZipInfo("dir/b.txt", (2024, 5, 6, 7, 8, 10))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, b"bravo" * 20)
    raw = buffer.getvalue()

    entries = pb.Greedy(entry).parse(raw)
    assert [e.name for e in entries] == ["a.txt", "dir/b.txt"]
    assert entries[0].method.name == "STORED" and entries[0].data == b"alpha"
    assert entries[0].modified == datetime(2024, 5, 6, 7, 8, 10)
    assert entries[0].crc32 == zlib.crc32(b"alpha")
    assert entries[1].method.name == "DEFLATED"
    assert zlib.decompress(entries[1].data, -15) == b"bravo" * 20
    rebuilt = b"".join(entry.build(e) for e in entries)
    assert raw.startswith(rebuilt)


def test_tar_archive():
    """
    A ustar archive written by `tarfile` parses into 512-byte headers (numbers stored
    as octal text) and data padded to 512 bytes, `Greedy` stopping at the zero
    blocks that end it; headers build back to the same bytes.
    """
    import tarfile
    from io import BytesIO

    this = pb.this

    def octal(width):
        return pb.Adapted(
            pb.PaddedString(width, "ascii"),
            lambda text: int(text.strip(" \x00") or "0", 8),
            lambda value: f"{round(value):0{width - 1}o}",
        )

    header = pb.Spec(
        {
            "name": pb.PaddedString(100),
            "mode": octal(8),
            "uid": octal(8),
            "gid": octal(8),
            "size": octal(12),
            "mtime": pb.Timestamp(octal(12)),
            "checksum": pb.Bytes(8),
            "type": pb.PaddedString(1, "ascii"),
            "linkname": pb.PaddedString(100),
            "magic": pb.Const(b"ustar\x0000", pb.Bytes(8)),
            "uname": pb.PaddedString(32),
            "gname": pb.PaddedString(32),
            "devmajor": pb.Bytes(8),
            "devminor": pb.Bytes(8),
            "prefix": pb.PaddedString(155),
            "pad": pb.Padding(12),
        }
    )
    member = pb.Spec(
        {"header": header, "data": pb.Aligned(512, pb.Bytes(this.header.size))}
    )
    tar = pb.Greedy(member)
    assert header.size == 512

    files = {"a.txt": b"alpha", "dir/b.txt": b"b" * 600}
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.uname = len(content), 1700000000, "pabo"
            archive.addfile(info, BytesIO(content))
    raw = buffer.getvalue()

    members = tar.parse(raw)
    assert {m.header.name: m.data for m in members} == files
    assert members[1].header.size == 600 and members[0].header.uname == "pabo"
    assert members[0].header.mtime.year == 2023 and members[0].header.type == "0"
    assert header.build(members[0].header) == raw[:512]
    assert len(member.build(members[1])) == 512 + 1024


def test_sqlite_header(tmp_path):
    """
    The 100-byte header of a database written by `sqlite3` parses (through the
    compiled single-`struct` path) and builds back to the same bytes.
    """
    import sqlite3
    from enum import IntEnum

    class Encoding(IntEnum):
        """
        SQLite text encodings.
        """

        UTF8 = 1
        UTF16LE = 2
        UTF16BE = 3

    sqlite = pb.Spec(
        {
            "magic": pb.Const(b"SQLite format 3\x00", pb.Bytes(16)),
            "page_size": pb.Adapted(
                pb.u16,
                lambda v: 65536 if v == 1 else v,
                lambda v: 1 if v == 65536 else v,
            ),
            "write_version": pb.u8,
            "read_version": pb.u8,
            "reserved": pb.u8,
            "max_fraction": pb.Const(64, pb.u8),
            "min_fraction": pb.Const(32, pb.u8),
            "leaf_fraction": pb.Const(32, pb.u8),
            "change_counter": pb.u32,
            "pages": pb.u32,
            "freelist_trunk": pb.u32,
            "freelist_pages": pb.u32,
            "schema_cookie": pb.u32,
            "schema_format": pb.u32,
            "cache_size": pb.u32,
            "vacuum_root": pb.u32,
            "encoding": pb.Enum(pb.u32, Encoding),
            "user_version": pb.u32,
            "incremental_vacuum": pb.u32,
            "application_id": pb.u32,
            "expansion": pb.Padding(20),
            "version_valid_for": pb.u32,
            "sqlite_version": pb.u32,
        },
        endian="big",
    )
    path = tmp_path / "test.db"
    db = sqlite3.connect(path)
    db.execute("PRAGMA user_version = 7")
    db.execute("PRAGMA application_id = 1234")
    db.execute("CREATE TABLE t (x)")
    db.commit()
    db.close()

    assert sqlite.size == 100
    data = sqlite.parse(path)
    assert data.user_version == 7 and data.application_id == 1234
    assert data.encoding is Encoding.UTF8 and data.pages >= 2
    assert 512 <= data.page_size <= 65536 and data.page_size & (data.page_size - 1) == 0
    assert sqlite.build(data) == path.read_bytes()[:100]


def test_npy_file():
    """
    A `.npy` file written by `np.save` parses into its text header and a float32
    array, and builds back to the same bytes.
    """
    from io import BytesIO

    import numpy as np

    npy = pb.Spec(
        {
            "magic": pb.Const(b"\x93NUMPY", pb.Bytes(6)),
            "major": pb.u8,
            "minor": pb.u8,
            "header": pb.PascalString(pb.u16, "latin-1"),
            "data": pb.Array(pb.f32),
        },
        endian="little",
    )
    array = np.linspace(0, 1, 10, dtype="<f4")
    buffer = BytesIO()
    np.save(buffer, array)
    raw = buffer.getvalue()

    data = npy.parse(raw)
    assert (data.major, data.minor) == (1, 0)
    assert "'descr': '<f4'" in data.header and "'shape': (10,)" in data.header
    assert np.array_equal(data.data, array)
    assert npy.build(data) == raw


def test_bmp_4bit_image():
    """
    A 4-bit BMP: a 16-colour palette and rows of 4-bit packed pixels, each row padded
    to 4 bytes. It builds to the right size and parses back to the same pixels.
    """
    import numpy as np

    this = pb.this
    bmp = pb.Spec(
        {
            "magic": pb.Const(b"BM", pb.Bytes(2)),
            "filesize": pb.u32,
            "reserved": pb.Padding(4),
            "offset": pb.u32,
            "dib_size": pb.Const(40, pb.u32),
            "width": pb.i32,
            "height": pb.i32,
            "planes": pb.Const(1, pb.u16),
            "bpp": pb.Const(4, pb.u16),
            "compression": pb.u32,
            "image_size": pb.u32,
            "xppm": pb.i32,
            "yppm": pb.i32,
            "colors": pb.Rebuild(pb.u32, pb.lenof(this.palette)),
            "important": pb.u32,
            "palette": pb.Repeat(
                pb.Spec({"b": pb.u8, "g": pb.u8, "r": pb.u8, "a": pb.u8}),
                this.colors,
            ),
            "rows": pb.Repeat(
                pb.Aligned(4, pb.Array(pb.u8, count=this.width, packing=4)),
                this.height,
            ),
        },
        endian="little",
    )
    width, height = 5, 3
    pixels = (np.arange(width * height, dtype=np.uint8) % 16).reshape(height, width)
    palette = [{"b": 17 * i, "g": 17 * i, "r": 17 * i, "a": 0} for i in range(16)]
    values = {
        "filesize": 14 + 40 + 64 + 4 * height,
        "offset": 14 + 40 + 64,
        "width": width,
        "height": height,
        "compression": 0,
        "image_size": 4 * height,
        "xppm": 2835,
        "yppm": 2835,
        "important": 0,
        "palette": palette,
        "rows": list(pixels),
    }
    raw = bmp.build(values)
    assert len(raw) == values["filesize"]
    # Row 0 is pixels 0..4 in nibbles, padded from 3 bytes to 4.
    assert raw[values["offset"] : values["offset"] + 4] == b"\x01\x23\x40\x00"
    data = bmp.parse(raw)
    assert data.colors == 16 and data.palette[15] == {
        "b": 255,
        "g": 255,
        "r": 255,
        "a": 0,
    }
    assert np.array_equal(np.array(data.rows), pixels)


def test_pcap_capture():
    """
    A pcap capture: a global header and a `Greedy` list of packet records, whose
    lengths are rebuilt from the data.
    """
    from enum import IntEnum

    this = pb.this

    class LinkType(IntEnum):
        """
        A few pcap link-layer types.
        """

        ETHERNET = 1
        RAW = 101

    record = pb.Spec(
        {
            "seconds": pb.u32,
            "microseconds": pb.u32,
            "captured": pb.Rebuild(pb.u32, pb.lenof(this.data)),
            "original": pb.u32,
            "data": pb.Bytes(this.captured),
        }
    )
    pcap = pb.Spec(
        {
            "magic": pb.Const(0xA1B2C3D4, pb.u32),
            "major": pb.u16,
            "minor": pb.u16,
            "thiszone": pb.i32,
            "sigfigs": pb.u32,
            "snaplen": pb.u32,
            "network": pb.Enum(pb.u32, LinkType),
            "packets": pb.Greedy(record),
        },
        endian="little",
    )
    values = {
        "major": 2,
        "minor": 4,
        "thiszone": 0,
        "sigfigs": 0,
        "snaplen": 65535,
        "network": LinkType.RAW,
        "packets": [
            {"seconds": 1, "microseconds": 500, "original": 3, "data": b"abc"},
            {"seconds": 2, "microseconds": 0, "original": 1500, "data": b"x" * 64},
        ],
    }
    raw = pcap.build(values)
    assert raw[:4] == b"\xd4\xc3\xb2\xa1" and len(raw) == 24 + 16 + 3 + 16 + 64
    data = pcap.parse(raw)
    assert data.network is LinkType.RAW and len(data.packets) == 2
    assert data.packets[1].captured == 64 and data.packets[1].data == b"x" * 64
    assert pcap.build(data) == raw


def test_dns_query():
    """
    A DNS query for `example.com`: a bit-field flags word, and names read as labels
    until the empty one. It parses and builds back to the same bytes.
    """
    this = pb.this
    name = pb.RepeatUntil(
        lambda label, ctx: label == "", pb.PascalString(pb.u8, "ascii")
    )
    question = pb.Spec({"name": name, "type": pb.u16, "class": pb.u16})
    dns = pb.Spec(
        {
            "id": pb.u16,
            "flags": pb.BitStruct(
                {
                    "response": pb.BitFlag(),
                    "opcode": pb.BitInt(4),
                    "authoritative": pb.BitFlag(),
                    "truncated": pb.BitFlag(),
                    "recursion_desired": pb.BitFlag(),
                    "recursion_available": pb.BitFlag(),
                    "zero": pb.BitPadding(3),
                    "rcode": pb.BitInt(4),
                }
            ),
            "qdcount": pb.Rebuild(pb.u16, pb.lenof(this.questions)),
            "ancount": pb.u16,
            "nscount": pb.u16,
            "arcount": pb.u16,
            "questions": pb.Repeat(question, this.qdcount),
        },
        endian="big",
    )
    raw = (
        bytes.fromhex("abcd 0100 0001 0000 0000 0000")
        + b"\x07example\x03com\x00"
        + b"\x00\x01\x00\x01"
    )
    data = dns.parse(raw)
    assert data.id == 0xABCD and data.flags.recursion_desired
    assert not data.flags.response and data.flags.opcode == 0
    assert data.questions == [{"name": ["example", "com", ""], "type": 1, "class": 1}]
    assert dns.build(data) == raw


def test_protobuf_wire_format():
    """
    The Protocol Buffers wire format: each field is a varint key (field number and
    wire type) and a value chosen by the wire type. The examples from the protobuf
    encoding guide parse and build back to the same bytes.
    """
    this = pb.this
    field = pb.Spec(
        {
            "key": pb.VarInt(),
            "number": pb.Computed(this.key >> 3),
            "value": pb.Switch(
                this.key & 7,
                {
                    0: pb.VarInt(),
                    1: pb.u64,
                    2: pb.Spec({"length": pb.VarInt(), "data": pb.Bytes(this.length)}),
                    5: pb.u32,
                },
            ),
        },
        endian="little",
    )
    message = pb.Greedy(field)
    # Field 1 = 150 (a varint), field 2 = "testing" (length-delimited).
    raw = bytes.fromhex("089601") + bytes.fromhex("120774657374696e67")
    data = message.parse(raw)
    assert [(f.number, f.key & 7) for f in data] == [(1, 0), (2, 2)]
    assert data[0].value == 150 and data[1].value.data == b"testing"
    assert message.build(data) == raw
    # A signed field (sint32) uses zigzag encoding: -2 is stored as 3.
    assert pb.ZigZag().parse(pb.VarInt().build(3)) == -2
