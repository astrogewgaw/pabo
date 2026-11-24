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
            lambda value: f"{value:0{width - 1}o}",
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
                    2: pb.Prefixed(pb.VarInt(), pb.GreedyBytes()),
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
    assert data[0].value == 150 and data[1].value == b"testing"
    assert message.build(data) == raw
    # A signed field (sint32) uses zigzag encoding: -2 is stored as 3.
    assert pb.ZigZag().parse(pb.VarInt().build(3)) == -2


def test_midi_file():
    """
    A MIDI file with one track (a tempo, a note on and off 128 ticks apart, and the
    end of the track) parses into its events, with big-order `VarInt` delta times
    and meta-event lengths, and builds back to the same bytes.
    """
    this = pb.this
    vlq = pb.VarInt(order="big")
    event = pb.Spec(
        {
            "delta": vlq,
            "status": pb.u8,
            "body": pb.Switch(
                this.status & 0xF0,
                {
                    0x80: pb.Spec({"note": pb.u8, "velocity": pb.u8}),
                    0x90: pb.Spec({"note": pb.u8, "velocity": pb.u8}),
                    0xB0: pb.Spec({"controller": pb.u8, "value": pb.u8}),
                    0xC0: pb.Spec({"program": pb.u8}),
                    0xF0: pb.Spec(
                        {"type": pb.u8, "data": pb.Prefixed(vlq, pb.GreedyBytes())}
                    ),
                },
            ),
        }
    )
    track = pb.Spec(
        {
            "id": pb.Const(b"MTrk", pb.Bytes(4)),
            "events": pb.Prefixed(pb.u32, pb.Greedy(event)),
        }
    )
    midi = pb.Spec(
        {
            "id": pb.Const(b"MThd", pb.Bytes(4)),
            "length": pb.Const(6, pb.u32),
            "format": pb.u16,
            "ntracks": pb.Rebuild(pb.u16, pb.lenof(this.tracks)),
            "division": pb.u16,
            "tracks": pb.Repeat(track, this.ntracks),
        },
        endian="big",
    )
    raw = (
        b"MThd"
        + bytes.fromhex("00000006 0000 0001 0060")
        + b"MTrk"
        + bytes.fromhex("00000014")
        + bytes.fromhex("00 ff 51 03 07a120")  # tempo: 500,000 us per beat
        + bytes.fromhex("00 90 3c 40")  # note on, middle C
        + bytes.fromhex("8100 80 3c 00")  # 128 ticks later, note off
        + bytes.fromhex("00 ff 2f 00")  # end of track
    )
    song = midi.parse(raw)
    assert song.division == 96 and song.ntracks == 1
    events = song.tracks[0].events
    assert [e.delta for e in events] == [0, 0, 128, 0]
    assert events[0].body == {"type": 0x51, "data": bytes.fromhex("07a120")}
    assert events[1].body == {"note": 60, "velocity": 64}
    assert events[3].body == {"type": 0x2F, "data": b""}
    assert midi.build(song) == raw


# Astronomy and space.


def _fitsvalue(text):
    """
    The value of a FITS header card (the text after `= `): a string, a logical,
    an int or a float. Comments after `/` are dropped.
    """
    text = text.strip()
    if text.startswith("'"):
        return text[1:].split("'")[0].rstrip()
    text = text.split("/")[0].strip()
    if text in ("T", "F"):
        return text == "T"
    try:
        return int(text)
    except ValueError:
        return float(text)


def _fitsheader():
    """
    A FITS header: 80-character cards up to `END`, padded with spaces to a
    multiple of 2880 bytes, plus a dict of its keyword values.
    """
    card = pb.PaddedString(80, "ascii", pad=" ")
    return pb.Spec(
        {
            "cards": pb.Aligned(
                2880,
                pb.RepeatUntil(lambda c, ctx: c.rstrip() == "END", card),
                fill=b" ",
            ),
            "meta": pb.Computed(
                lambda ctx: {
                    c[:8].rstrip(): _fitsvalue(c[10:])
                    for c in ctx.cards
                    if c[8:10] == "= "
                }
            ),
        }
    )


def _fitscards(pairs):
    """
    Fixed-format FITS cards for (keyword, value) pairs, followed by `END`.
    """
    cards = []
    for key, value in pairs:
        if isinstance(value, bool):
            cards.append(f"{key:<8}= {'T' if value else 'F':>20}")
        elif isinstance(value, str):
            cards.append(f"{key:<8}= '{value:<8}'")
        else:
            cards.append(f"{key:<8}= {value:>20}")
    return [*cards, "END"]


def test_fits_image():
    """
    A FITS file with a 16-bit image: the header's cards parse into a dict, `BITPIX`
    picks the big-endian type, the `NAXISn` values give the number of pixels, and
    both parts are padded to 2880 bytes.
    """
    import math

    import numpy as np

    BITPIX = {8: pb.u8, 16: pb.i16, 32: pb.i32, 64: pb.i64, -32: pb.f32, -64: pb.f64}

    def pixels(ctx):
        meta = ctx.header.meta
        return math.prod(meta[f"NAXIS{i}"] for i in range(1, meta["NAXIS"] + 1))

    fits = pb.Spec(
        {
            "header": _fitsheader(),
            "data": pb.Aligned(
                2880,
                pb.Switch(
                    lambda ctx: ctx.header.meta["BITPIX"],
                    {
                        bitpix: pb.Array(dtype, count=pixels)
                        for bitpix, dtype in BITPIX.items()
                    },
                ),
            ),
        },
        endian="big",
    )
    image = np.arange(12, dtype=">i2").reshape(3, 4) - 6
    cards = _fitscards(
        [
            ("SIMPLE", True),
            ("BITPIX", 16),
            ("NAXIS", 2),
            ("NAXIS1", 4),
            ("NAXIS2", 3),
            ("OBJECT", "M31"),
            ("EXPTIME", 30.5),
        ]
    )
    raw = fits.build({"header": {"cards": cards}, "data": image.ravel()})
    assert len(raw) == 2 * 2880
    assert raw[:30] == b"SIMPLE  =                    T"
    assert raw[8 * 80 : 8 * 80 + 3] == b"   " and raw[-1:] == b"\x00"

    data = fits.parse(raw)
    assert data.header.meta == {
        "SIMPLE": True,
        "BITPIX": 16,
        "NAXIS": 2,
        "NAXIS1": 4,
        "NAXIS2": 3,
        "OBJECT": "M31",
        "EXPTIME": 30.5,
    }
    # NAXIS1 varies fastest, so the array is (NAXIS2, NAXIS1).
    assert np.array_equal(data.data.reshape(3, 4), image)


def test_fits_binary_table():
    """
    A FITS binary table extension: `Deferred` makes the row specification from the
    header's `TFORMn` and `TTYPEn` cards, then the rows are parsed and built with
    it.
    """
    TFORM = {
        "B": pb.u8,
        "I": pb.i16,
        "J": pb.i32,
        "K": pb.i64,
        "E": pb.f32,
        "D": pb.f64,
    }

    def rowspec(meta):
        fields = {}
        for i in range(1, meta["TFIELDS"] + 1):
            form = meta[f"TFORM{i}"]
            repeat, code = int(form[:-1] or 1), form[-1]
            if code == "A":
                field = pb.PaddedString(repeat, "ascii", pad=" ")
            elif repeat == 1:
                field = TFORM[code]
            else:
                field = pb.Array(TFORM[code], count=repeat)
            fields[meta.get(f"TTYPE{i}", f"COL{i}")] = field
        return pb.Spec(fields, endian="big")

    def rows(ctx):
        meta = ctx.header.meta
        return pb.Repeat(rowspec(meta), meta["NAXIS2"])

    table = pb.Spec(
        {
            "header": _fitsheader(),
            "rows": pb.Aligned(2880, pb.Deferred(rows)),
        }
    )
    cards = _fitscards(
        [
            ("XTENSION", "BINTABLE"),
            ("BITPIX", 8),
            ("NAXIS", 2),
            ("NAXIS1", 20),
            ("NAXIS2", 3),
            ("PCOUNT", 0),
            ("GCOUNT", 1),
            ("TFIELDS", 3),
            ("TTYPE1", "ID"),
            ("TFORM1", "1J"),
            ("TTYPE2", "NAME"),
            ("TFORM2", "8A"),
            ("TTYPE3", "FLUX"),
            ("TFORM3", "1D"),
        ]
    )
    values = [{"ID": i, "NAME": f"SRC{i}", "FLUX": 1.5 * i} for i in range(3)]
    raw = table.build({"header": {"cards": cards}, "rows": values})
    assert len(raw) == 2 * 2880
    assert raw[2880:2884] == b"\x00\x00\x00\x00" and raw[2884:2892] == b"SRC0    "

    hdu = table.parse(raw)
    meta = hdu.header.meta
    assert meta["XTENSION"] == "BINTABLE" and meta["NAXIS1"] == 20
    assert hdu.rows == values


def test_ccsds_space_packets():
    """
    CCSDS space packets: a 6-byte header of bit fields whose length field is the
    data length minus one. A packet builds to the expected bytes and a stream of
    them parses with `Greedy`.
    """
    this = pb.this
    packet = pb.Spec(
        {
            "header": pb.BitStruct(
                {
                    "version": pb.BitInt(3),
                    "type": pb.BitInt(1),
                    "secondary": pb.BitFlag(),
                    "apid": pb.BitInt(11),
                    "sequence": pb.BitInt(2),
                    "count": pb.BitInt(14),
                }
            ),
            "length": pb.Rebuild(pb.u16, pb.lenof(this.data) - 1),
            "data": pb.Bytes(this.length + 1),
        },
        endian="big",
    )
    header = {
        "version": 0,
        "type": 0,
        "secondary": True,
        "apid": 0x123,
        "sequence": 3,
        "count": 42,
    }
    raw = packet.build({"header": header, "data": b"hello"})
    # 000 0 1 00100100011 | 11 00000000101010 | length 4
    assert raw == bytes.fromhex("0923 c02a 0004") + b"hello"
    stream = raw + packet.build({"header": {**header, "count": 43}, "data": b"!"})
    packets = pb.Greedy(packet).parse(stream)
    assert [p.header.count for p in packets] == [42, 43]
    assert packets[1].length == 0 and packets[1].data == b"!"


def test_vdif_frame():
    """
    A VDIF frame: a header of four little-endian words of bit fields (and four
    more of extended data, unless the legacy bit is set), with its time computed
    from the reference epoch, then 2-bit samples, oldest in the lowest bits.
    """
    from datetime import datetime, timedelta, timezone

    import numpy as np

    this = pb.this

    def word(fields):
        return pb.BitStruct(fields, bitorder="little")

    def start(ctx):
        epoch = ctx.header.w1.epoch  # half-years since 2000
        origin = datetime(
            2000 + epoch // 2, 1 + 6 * (epoch % 2), 1, tzinfo=timezone.utc
        )
        return origin + timedelta(seconds=ctx.header.w0.seconds)

    header = pb.Spec(
        {
            "w0": word(
                {
                    "seconds": pb.BitInt(30),
                    "legacy": pb.BitFlag(),
                    "invalid": pb.BitFlag(),
                }
            ),
            "w1": word(
                {
                    "frame": pb.BitInt(24),
                    "epoch": pb.BitInt(6),
                    "unassigned": pb.BitPadding(2),
                }
            ),
            "w2": word(
                {
                    "length": pb.BitInt(24),
                    "log2nchan": pb.BitInt(5),
                    "version": pb.BitInt(3),
                }
            ),
            "w3": word(
                {
                    "station": pb.BitInt(16),
                    "thread": pb.BitInt(10),
                    "bitsm1": pb.BitInt(5),
                    "complex": pb.BitFlag(),
                }
            ),
            "extended": pb.If(this.w0.legacy == 0, pb.Bytes(16)),
        }
    )
    frame = pb.Spec(
        {
            "header": header,
            "time": pb.Computed(start),
            "samples": pb.Array(
                pb.u8,
                count=lambda ctx: (
                    4 * (8 * ctx.header.w2.length - header.sizeof(ctx.header))
                ),
                packing=2,
                bitorder="little",
            ),
        }
    )
    samples = (np.arange(128) % 4).astype(np.uint8)
    values = {
        "header": {
            "w0": {"seconds": 12345, "legacy": False, "invalid": False},
            "w1": {"frame": 7, "epoch": 49},
            "w2": {"length": 8, "log2nchan": 0, "version": 0},
            "w3": {"station": 0x4767, "thread": 1, "bitsm1": 1, "complex": False},
            "extended": bytes(16),
        },
        "samples": samples,
    }
    raw = frame.build(values)
    assert len(raw) == 8 * 8
    assert raw[:4] == (12345).to_bytes(4, "little")
    assert raw[4:8] == (7 | 49 << 24).to_bytes(4, "little")
    assert raw[12:16] == (0x4767 | 1 << 16 | 1 << 26).to_bytes(4, "little")
    assert raw[32] == 0b11_10_01_00  # samples 0, 1, 2, 3 from bit 0 up
    data = frame.parse(raw)
    # Epoch 49 is the second half of 2024.
    assert data.time == datetime(2024, 7, 1, 3, 25, 45, tzinfo=timezone.utc)
    assert data.header.w3.bitsm1 + 1 == 2 and np.array_equal(data.samples, samples)

    # In legacy mode, the header is 16 bytes and the data 48.
    values["header"]["w0"]["legacy"] = True
    del values["header"]["extended"]
    values["samples"] = (np.arange(4 * 48) % 4).astype(np.uint8)
    legacy = frame.parse(frame.build(values))
    assert legacy.header.extended is None and len(legacy.samples) == 4 * 48


def _dafspec():
    """
    A SPICE DAF (here an SPK ephemeris): the file record, then the first summary
    record and its names, in the byte order the file record states.
    """
    this = pb.this

    def body(endian):
        summary = pb.Spec(
            {
                "start": pb.f64,  # TDB seconds past J2000
                "stop": pb.f64,
                "target": pb.i32,
                "center": pb.i32,
                "frame": pb.i32,
                "type": pb.i32,
                "begin": pb.i32,  # 1-based 8-byte word addresses
                "end": pb.i32,
            }
        )
        return pb.Spec(
            {
                "nd": pb.Const(2, pb.i32),
                "ni": pb.Const(6, pb.i32),
                "name": pb.PaddedString(60, "ascii", pad=" "),
                "fward": pb.i32,
                "bward": pb.i32,
                "free": pb.i32,
                "format": pb.Bytes(8),
                "prenul": pb.Padding(603),
                "ftp": pb.Const(
                    b"FTPSTR:\r:\n:\r\n:\r\x00:\x81:\x10\xce:ENDFTP", pb.Bytes(28)
                ),
                "pstnul": pb.Padding(297),
                "record": pb.Pointer(
                    (this.fward - 1) * 1024,
                    pb.Spec(
                        {
                            "next": pb.f64,
                            "prev": pb.f64,
                            "nsum": pb.f64,
                            "summaries": pb.Repeat(summary, lambda ctx: int(ctx.nsum)),
                        }
                    ),
                ),
                "names": pb.Pointer(
                    this.fward * 1024,
                    pb.Repeat(
                        pb.PaddedString(40, "ascii", pad=" "),
                        lambda ctx: int(ctx.record.nsum),
                    ),
                ),
            },
            endian=endian,
        )

    return pb.Spec(
        {
            "id": pb.PaddedString(8, "ascii", pad=" "),
            "format": pb.Peek(pb.Pointer(88, pb.PaddedString(8, "ascii"))),
            "body": pb.Switch(
                this.format, {"LTL-IEEE": body("little"), "BIG-IEEE": body("big")}
            ),
        }
    )


def test_spice_daf():
    """
    A small SPK file, written by hand in both byte orders: the file record's byte
    order string picks the endianness, and pointers follow it to the summary and
    name records.
    """
    import struct

    daf = _dafspec()
    ftp = b"FTPSTR:\r:\n:\r\n:\r\x00:\x81:\x10\xce:ENDFTP"
    for prefix, fmt in (("<", b"LTL-IEEE"), (">", b"BIG-IEEE")):
        record = (
            b"DAF/SPK "
            + struct.pack(prefix + "ii", 2, 6)
            + b"NIO2SPK".ljust(60)
            + struct.pack(prefix + "iii", 2, 2, 1000)
            + fmt
            + bytes(603)
            + ftp
            + bytes(297)
        )
        summaries = struct.pack(prefix + "ddd", 0, 0, 2) + b"".join(
            struct.pack(prefix + "dd6i", -3e9, 3e9, target, 0, 1, 2, begin, begin + 99)
            for target, begin in ((399, 385), (301, 485))
        )
        names = b"EARTH".ljust(40) + b"MOON".ljust(40)
        raw = record + summaries.ljust(1024, b"\x00") + names.ljust(1024, b" ")
        assert len(record) == 1024

        data = daf.parse(raw)
        assert data.id == "DAF/SPK" and data.format == fmt.decode()
        body = data.body
        assert body.name == "NIO2SPK" and body.fward == 2 and body.free == 1000
        assert [s.target for s in body.record.summaries] == [399, 301]
        assert (
            body.record.summaries[1].begin == 485
            and body.record.summaries[0].start == -3e9
        )
        assert body.names == ["EARTH", "MOON"]


def test_ser_video():
    """
    A SER video (from planetary cameras): a 178-byte little-endian header, 16-bit
    frames, and the optional trailer of per-frame UTC times, stored as 100 ns ticks
    since the year 1 (of which only the low 62 bits are used).
    """
    import struct
    from datetime import datetime, timedelta, timezone

    import numpy as np

    this = pb.this
    ticks = pb.Timestamp(
        pb.Adapted(
            pb.i64,
            lambda t: (t & (2**62 - 1)) // 10,  # 100 ns ticks to microseconds
            lambda us: us * 10,
        ),
        epoch=datetime(1, 1, 1),
        unit="us",
    )
    ser = pb.Spec(
        {
            "id": pb.Const(b"LUCAM-RECORDER", pb.Bytes(14)),
            "luid": pb.i32,
            "color": pb.i32,  # 0 is mono, 8-19 Bayer patterns, 100 RGB, 101 BGR
            "littleendian": pb.i32,
            "width": pb.i32,
            "height": pb.i32,
            "depth": pb.i32,  # bits per pixel per plane
            "nframes": pb.i32,
            "observer": pb.PaddedString(40, "ascii"),
            "instrument": pb.PaddedString(40, "ascii"),
            "telescope": pb.PaddedString(40, "ascii"),
            "start": ticks,  # local time
            "start_utc": ticks,
            "frames": pb.Repeat(
                pb.Array(pb.u16, count=this.width * this.height), this.nframes
            ),
            "times": pb.Optional(pb.Repeat(ticks, this.nframes)),
        },
        endian="little",
    )
    start = datetime(2024, 3, 1, 21, 0, tzinfo=timezone.utc)
    frames = [np.full(6, 1000 * i, dtype="<u2") for i in range(3)]
    values = {
        "luid": 0,
        "color": 0,
        "littleendian": 0,
        "width": 3,
        "height": 2,
        "depth": 12,
        "nframes": 3,
        "observer": "pabo",
        "instrument": "camera",
        "telescope": "C11",
        "start": start,
        "start_utc": start,
        "frames": frames,
        "times": [start + timedelta(milliseconds=20 * i) for i in range(3)],
    }
    raw = ser.build(values)
    assert len(raw) == 178 + 3 * 12 + 3 * 8
    assert raw[42:46] == b"pabo" and raw[46:82] == bytes(36)
    # 2024-03-01T21:00 as .NET ticks.
    elapsed = start.replace(tzinfo=None) - datetime(1, 1, 1)
    expected = (elapsed.days * 86400 + elapsed.seconds) * 10**7
    assert struct.unpack("<q", raw[170:178])[0] == expected

    data = ser.parse(raw)
    assert data.depth == 12 and data.frames[2][0] == 2000
    assert data.times[1] == start + timedelta(milliseconds=20)
    # The trailer is optional.
    assert ser.parse(raw[: -3 * 8]).times is None
    # The top two bits of a timestamp (a .NET DateTimeKind) are ignored.
    flagged = raw[:170] + struct.pack("<q", expected | 1 << 62) + raw[178:]
    assert ser.parse(flagged).start_utc == start


def test_mark5b_frame():
    """
    A Mark 5B frame: four little-endian header words (a sync word, bit fields,
    and a BCD time code whose day is the MJD modulo 1000), then 10,000 bytes of
    data. The time needs the thousands of the MJD from elsewhere.
    """
    from datetime import datetime, timedelta, timezone

    def bcd(wraps):
        """
        Decimal digits stored one per 4 bits (BCD), as an int.
        """
        return pb.Adapted(wraps, lambda v: int(f"{v:x}"), lambda d: int(str(d), 16))

    mark5b = pb.Spec(
        {
            "sync": pb.Const(0xABADDEED, pb.u32),
            "w1": pb.BitStruct(
                {
                    "frame": pb.BitInt(15),
                    "tvg": pb.BitFlag(),
                    "user": pb.BitInt(12),
                    "years": pb.BitInt(4),  # since 2000, in later recorders
                },
                bitorder="little",
            ),
            "jjjsssss": bcd(pb.u32),  # MJD % 1000, then seconds of the day
            "crc": pb.u16,
            "fraction": bcd(pb.u16),  # .SSSS, in units of 0.1 ms
            "data": pb.Bytes(10000),
        },
        endian="little",
    )
    header = {
        "w1": {"frame": 5, "tvg": False, "user": 0xABC, "years": 4},
        "jjjsssss": 46012345,  # MJD ...460, second 12345
        "crc": 0xBEEF,
        "fraction": 1250,
    }
    raw = mark5b.build({**header, "data": bytes(10000)})
    assert len(raw) == 10016
    assert raw[:4] == b"\xed\xde\xad\xab"
    assert raw[8:12] == bytes.fromhex("45230146")  # BCD 0x46012345, little-endian
    assert raw[12:16] == bytes.fromhex("efbe 5012")

    data = mark5b.parse(raw)
    assert data.w1.frame == 5 and data.w1.years == 4 and data.fraction == 1250
    mjd = 60000 + data.jjjsssss // 100000  # the thousands come from elsewhere
    seconds = data.jjjsssss % 100000 + data.fraction / 10000
    time = datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(mjd, seconds)
    assert time == datetime(2024, 5, 30, 3, 25, 45, 125000, tzinfo=timezone.utc)


def test_psrdada_file():
    """
    A PSRDADA file: an ASCII header of `KEY value` lines (with `#` comments),
    padded with NULs to `HDR_SIZE` bytes, a size given in the header itself, then
    8-bit samples.
    """
    import numpy as np

    this = pb.this

    def parse(text):
        pairs = (line.split("#")[0].split(None, 1) for line in text.splitlines())
        return {pair[0]: pair[1].strip() for pair in pairs if len(pair) == 2}

    def format(header):
        return "".join(f"{key} {value}\n" for key, value in header.items())

    dada = pb.Spec(
        {
            # HDR_SIZE is inside the header, so peek at the text up to the first
            # NUL to find it before reading the whole block.
            "size": pb.Peek(
                pb.Adapted(
                    pb.CString("ascii"), lambda t: int(parse(t)["HDR_SIZE"]), str
                )
            ),
            "header": pb.Adapted(pb.PaddedString(this.size, "ascii"), parse, format),
            "data": pb.Array(pb.i8),
        }
    )
    text = (
        "# A test observation\n"
        "HDR_VERSION 1.0\n"
        "HDR_SIZE    4096\n"
        "UTC_START   2024-03-01-21:00:00\n"
        "OBS_OFFSET  0\n"
        "NBIT        8\n"
        "NCHAN       4\n"
        "NPOL        1\n"
        "NDIM        1\n"
        "TSAMP       64.0     # microseconds\n"
        "SOURCE      J0437-4715\n"
    )
    samples = np.arange(-8, 8, dtype=np.int8)
    raw = text.encode().ljust(4096, b"\x00") + samples.tobytes()

    data = dada.parse(raw)
    assert data.size == 4096
    assert data.header["TSAMP"] == "64.0" and data.header["SOURCE"] == "J0437-4715"
    assert int(data.header["NCHAN"]) == 4 and np.array_equal(data.data, samples)
    rebuilt = dada.build({"size": 4096, "header": data.header, "data": samples})
    assert len(rebuilt) == 4096 + 16 and dada.parse(rebuilt).header == data.header
