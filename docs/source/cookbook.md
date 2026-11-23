# Cookbook

Real formats, written with pabo. Each recipe is tested in `tests/test_cookbook.py`,
against files written by Python's standard library or numpy where it can make
them. All of them start with:

```python
import pabo as pb
from pabo import lenof, this
```

## Images and sound

### PNG header

```python
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
```

### BMP image with a 16-colour palette

Each pixel is 4 bits, so a row is a bit-packed `Array`, and every row is padded to
a multiple of 4 bytes with `Aligned`. The number of palette entries is filled in
when building.

```python
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
        "colors": pb.Rebuild(pb.u32, lenof(this.palette)),
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

image = bmp.parse("icon.bmp")
image.rows[0]    # the bottom row's palette indices, as a numpy array
```

### WAV (RIFF) audio

Chunk sizes are computed when building, with `Rebuild`, and each chunk's fields
are embedded so they sit next to the chunk's id and size.

```python
def chunk(tag, body, size):
    return pb.Spec(
        {
            "id": pb.Const(tag, pb.Bytes(4)),
            "size": pb.Rebuild(pb.u32, size),
            "_": pb.Embedded(body),
        }
    )

fmt = pb.Spec(
    {
        "audio_format": pb.u16,
        "channels": pb.u16,
        "rate": pb.u32,
        "byte_rate": pb.Rebuild(pb.u32, this.rate * this.channels * this.bits // 8),
        "block_align": pb.Rebuild(pb.u16, this.channels * this.bits // 8),
        "bits": pb.u16,
    }
)
samples = pb.Spec({"samples": pb.Array(pb.i16, count=this.size // 2)})

wav = pb.Spec(
    {
        "riff": pb.Const(b"RIFF", pb.Bytes(4)),
        "size": pb.Rebuild(pb.u32, 36 + 2 * lenof(this.data.samples)),
        "wave": pb.Const(b"WAVE", pb.Bytes(4)),
        "fmt": chunk(b"fmt ", fmt, lambda ctx: 16),
        "data": chunk(b"data", samples, 2 * lenof(this.samples)),
        "end": pb.Terminated(),
    },
    endian="little",
)

audio = wav.parse("tone.wav")
audio.fmt.rate, audio.data.samples
```

## Archives

### gzip header

Which optional fields follow the fixed ones depends on bits of the flags byte,
so each is an `If` on a bitwise expression. The modification time is a Unix
timestamp.

```python
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

data = gz.parse("notes.txt.gz")
data.header.name, data.header.mtime
```

The rest is raw deflate data followed by an 8-byte trailer (a CRC-32 and the
uncompressed size): `zlib.decompress(data.rest[:-8], -15)` gives the contents.

### ZIP entries

A ZIP file starts with its entries, each a header, a name and the data. The
lengths of the name and data are filled in when building, the compression method
is an `Enum`, and the MS-DOS date and time (two packed `u16`s) are turned into a
`datetime` with `Adapted`. `Greedy` reads entries until the central directory,
whose signature no longer matches the `Const`.

```python
from datetime import datetime
from enum import IntEnum

class Method(IntEnum):
    STORED = 0
    DEFLATED = 8

def dostime(v):
    return datetime(
        1980 + (v >> 25), (v >> 21) & 15, (v >> 16) & 31,
        (v >> 11) & 31, (v >> 5) & 63, (v & 31) * 2,
    )

def fromdatetime(d):
    return (
        (d.year - 1980) << 25 | d.month << 21 | d.day << 16
        | d.hour << 11 | d.minute << 5 | d.second // 2
    )

entry = pb.Spec(
    {
        "signature": pb.Const(b"PK\x03\x04", pb.Bytes(4)),
        "version": pb.u16,
        "flags": pb.u16,
        "method": pb.Enum(pb.u16, Method),
        "modified": pb.Adapted(pb.u32, dostime, fromdatetime),
        "crc32": pb.u32,
        "csize": pb.Rebuild(pb.u32, lenof(this.data)),
        "usize": pb.u32,
        "namelen": pb.Rebuild(pb.u16, lenof(this.name)),
        "extralen": pb.Rebuild(pb.u16, lenof(this.extra)),
        "name": pb.PaddedString(this.namelen),
        "extra": pb.Bytes(this.extralen),
        "data": pb.Bytes(this.csize),
    },
    endian="little",
)

for e in pb.Greedy(entry).parse("archive.zip"):
    print(e.name, e.method.name, e.modified)
```

Deflated data is decompressed with `zlib.decompress(e.data, -15)`.

### tar archive

A tar file is a list of 512-byte headers, each followed by the file's data padded
to 512 bytes. Numbers are stored as octal text, which `Adapted` turns into ints.
`Greedy` stops at the blocks of zeros that end the archive.

```python
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
member = pb.Spec({"header": header, "data": pb.Aligned(512, pb.Bytes(this.header.size))})
tar = pb.Greedy(member)

files = {m.header.name: m.data for m in tar.parse("backup.tar")}
```

## Data files

### SQLite database header

The first 100 bytes of every SQLite database. A specification of fixed-size
fields like this one is compiled into a single `struct` call.

```python
from enum import IntEnum

class Encoding(IntEnum):
    UTF8 = 1
    UTF16LE = 2
    UTF16BE = 3

sqlite = pb.Spec(
    {
        "magic": pb.Const(b"SQLite format 3\x00", pb.Bytes(16)),
        "page_size": pb.Adapted(  # 1 means 65536
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

sqlite.parse("app.db").user_version
```

### NumPy `.npy` file

A magic string, a version, a text header (the dtype and shape, as a Python
literal) prefixed by its length, then the array. Parsing a file by path
memory-maps it, so the array is a view of the file and is not copied.

```python
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

saved = npy.parse("weights.npy")
saved.header.strip()    # "{'descr': '<f4', 'fortran_order': False, 'shape': (10,), }"
```

This recipe assumes little-endian `float32` data; use `ast.literal_eval` on the
header to check the dtype and reshape the array.

## Executables

### ELF header

The endianness of an ELF file is given by a byte in its header, and the size of
its addresses by another. `Switch` picks a body with the right endianness, and
`If` picks the address size.

```python
def body(endian):
    is64 = this._.ident.cls == 2
    addr = pb.If(is64, pb.u64, pb.u32)
    return pb.Spec(
        {
            "type": pb.u16, "machine": pb.u16, "version": pb.u32,
            "entry": addr, "phoff": addr, "shoff": addr,
            "flags": pb.u32, "ehsize": pb.u16,
            "phentsize": pb.u16, "phnum": pb.u16,
            "shentsize": pb.u16, "shnum": pb.u16, "shstrndx": pb.u16,
        },
        endian=endian,
    )

elf = pb.Spec(
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
        "header": pb.Switch(this.ident.data, {1: body("little"), 2: body("big")}),
    }
)

elf.parse("/bin/ls").header.machine
```

## Networking

### IPv4 header

The first byte and the fragment word hold fields narrower than a byte, so they
are `BitStruct`s. The header length (`ihl`, in 4-byte words) says how many bytes
of options follow.

```python
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
```

### DNS query

The flags are a 16-bit `BitStruct`. A name is a list of labels, each prefixed by
its length and ending with an empty one, which makes it a `RepeatUntil`. The
question count is filled in when building.

```python
label = pb.PascalString(pb.u8, "ascii")
name = pb.RepeatUntil(lambda part, ctx: part == "", label)
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
        "qdcount": pb.Rebuild(pb.u16, lenof(this.questions)),
        "ancount": pb.u16,
        "nscount": pb.u16,
        "arcount": pb.u16,
        "questions": pb.Repeat(question, this.qdcount),
    },
    endian="big",
)

query = {
    "id": 0xABCD,
    "flags": {
        "response": False,
        "opcode": 0,
        "authoritative": False,
        "truncated": False,
        "recursion_desired": True,
        "recursion_available": False,
        "rcode": 0,
    },
    "ancount": 0,
    "nscount": 0,
    "arcount": 0,
    "questions": [{"name": ["example", "com", ""], "type": 1, "class": 1}],
}
dns.build(query)    # ready to send over UDP to port 53
```

### pcap capture

A packet capture (as written by tcpdump or Wireshark) is a header, then packets
until the end of the file, each with its captured length in front.

```python
from enum import IntEnum

class LinkType(IntEnum):
    ETHERNET = 1
    RAW = 101

record = pb.Spec(
    {
        "seconds": pb.u32,
        "microseconds": pb.u32,
        "captured": pb.Rebuild(pb.u32, lenof(this.data)),
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

capture = pcap.parse("traffic.pcap")
len(capture.packets)
```

This reads little-endian captures with microsecond timestamps, the most common
kind; others have a different magic number.

## Serialization

### Protocol Buffers wire format

A protobuf message is a list of fields. Each starts with a varint key holding the
field number and a wire type, and the wire type says how the value is stored.
Without the message's schema, this reads the raw fields.

```python
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

message.parse(bytes.fromhex("089601"))    # field 1 = 150
```

Signed `sint32`/`sint64` values are zigzag-encoded: read them with `pb.ZigZag()`.
