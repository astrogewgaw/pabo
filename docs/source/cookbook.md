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

### MIDI file

A Standard MIDI File is a header chunk and then track chunks of events. The time
before each event, and the length of each meta event's data, are variable-length
quantities: 7 bits per byte, most significant first, which is
`VarInt(order="big")`. The kind of event is in the top 4 bits of its status byte.

```python
vlq = pb.VarInt(order="big")
event = pb.Spec(
    {
        "delta": vlq,
        "status": pb.u8,
        "body": pb.Switch(
            this.status & 0xF0,
            {
                0x80: pb.Spec({"note": pb.u8, "velocity": pb.u8}),  # note off
                0x90: pb.Spec({"note": pb.u8, "velocity": pb.u8}),  # note on
                0xB0: pb.Spec({"controller": pb.u8, "value": pb.u8}),
                0xC0: pb.Spec({"program": pb.u8}),
                0xF0: pb.Spec({"type": pb.u8, "data": pb.Prefixed(vlq, pb.GreedyBytes())}),
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
        "ntracks": pb.Rebuild(pb.u16, lenof(this.tracks)),
        "division": pb.u16,
        "tracks": pb.Repeat(track, this.ntracks),
    },
    endian="big",
)

song = midi.parse("song.mid")
[e.body.note for e in song.tracks[0].events if e.status & 0xF0 == 0x90]
```

This handles the common events and meta events (status `0xFF`). Real files often
use *running status*, where an event leaves out its status byte when it is the
same as the previous one; that needs the previous event's status, which a
custom construct can keep (see [](custom.md)).

## Archives

### gzip file

Which optional fields follow the fixed ones depends on bits of the flags byte,
so each is an `If` on a bitwise expression. The modification time is a Unix
timestamp. Then comes the compressed data, up to an 8-byte trailer (a CRC-32 and
the size of the data): `Remaining` reads up to the trailer, `Transformed`
decompresses it, and `Rebuild` fills in the trailer when building.

```python
import zlib

def deflate(data):
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # raw deflate, as gzip does
    return compressor.compress(data) + compressor.flush()

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
gz = pb.Spec(
    {
        "header": header,
        "data": pb.Remaining(
            pb.Transformed(pb.GreedyBytes(), lambda raw: zlib.decompress(raw, -15), deflate),
            leave=8,
        ),
        "crc32": pb.Rebuild(pb.u32, lambda ctx: zlib.crc32(ctx.data)),
        "size": pb.Rebuild(pb.u32, lambda ctx: len(ctx.data) % 2**32),
    },
    endian="little",
)

notes = gz.parse("notes.txt.gz")
notes.header.name, notes.data
```

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

Deflated data is decompressed with `zlib.decompress(e.data, -15)`. The archive
ends with a 22-byte record (when it has no comment) giving the number of entries
and where the central directory, the archive's index, starts; a `Pointer` with
`whence=2` reads it from the end:

```python
end = pb.Spec(
    {
        "signature": pb.Const(b"PK\x05\x06", pb.Bytes(4)),
        "disk": pb.u16,
        "directory_disk": pb.u16,
        "disk_entries": pb.u16,
        "entries": pb.u16,
        "directory_size": pb.u32,
        "directory_offset": pb.u32,
        "comment_length": pb.u16,
    },
    endian="little",
)

pb.Pointer(-22, end, whence=2).parse("archive.zip").entries
```

### tar archive

A tar file is a list of 512-byte headers, each followed by the file's data padded
to 512 bytes. Numbers are stored as octal text, which `Adapted` turns into ints.
`Greedy` stops at the blocks of zeros that end the archive.

```python
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
                2: pb.Prefixed(pb.VarInt(), pb.GreedyBytes()),
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

## Astronomy and space

### FITS image

A FITS header is a list of 80-character text cards ending with `END`, padded with
spaces to a multiple of 2880 bytes. The cards are read as strings and turned into
a dict of keyword values. `BITPIX` gives the type of the (big-endian) pixels,
and the `NAXISn` values their number; the data is padded to 2880 bytes too.

```python
import math

def value(text):
    text = text.strip()
    if text.startswith("'"):
        return text[1:].split("'")[0].rstrip()
    text = text.split("/")[0].strip()  # drop the comment
    if text in ("T", "F"):
        return text == "T"
    try:
        return int(text)
    except ValueError:
        return float(text)

card = pb.PaddedString(80, "ascii", pad=" ")
header = pb.Spec(
    {
        "cards": pb.Aligned(
            2880,
            pb.RepeatUntil(lambda c, ctx: c.rstrip() == "END", card),
            fill=b" ",
        ),
        "meta": pb.Computed(
            lambda ctx: {
                c[:8].rstrip(): value(c[10:]) for c in ctx.cards if c[8:10] == "= "
            }
        ),
    }
)

BITPIX = {8: pb.u8, 16: pb.i16, 32: pb.i32, 64: pb.i64, -32: pb.f32, -64: pb.f64}

def pixels(ctx):
    meta = ctx.header.meta
    return math.prod(meta[f"NAXIS{i}"] for i in range(1, meta["NAXIS"] + 1))

fits = pb.Spec(
    {
        "header": header,
        "data": pb.Aligned(
            2880,
            pb.Switch(
                lambda ctx: ctx.header.meta["BITPIX"],
                {bitpix: pb.Array(dtype, count=pixels) for bitpix, dtype in BITPIX.items()},
            ),
        ),
    },
    endian="big",
)

hdu = fits.parse("galaxy.fits")
image = hdu.data.reshape(hdu.header.meta["NAXIS2"], hdu.header.meta["NAXIS1"])
```

This reads the primary image. `BSCALE` and `BZERO`, if present, scale the stored
values: `BZERO + BSCALE * image`.

### FITS binary table

The columns of a FITS table are described by `TFORMn` (a repeat count and a type
code) and `TTYPEn` (a name) cards, so the layout of a row is only known once the
header has been read. `Deferred` makes the row specification from the header
when it gets to the rows. (A `Repeat` of a fixed-size specification is parsed in
bulk, so this is fast.)

```python
TFORM = {"B": pb.u8, "I": pb.i16, "J": pb.i32, "K": pb.i64, "E": pb.f32, "D": pb.f64}

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
        "header": header,  # as in the image recipe
        "rows": pb.Aligned(2880, pb.Deferred(rows)),
    }
)

hdu = table.parse(raw)    # the bytes of a BINTABLE extension
hdu.rows[0]["FLUX"]
```

This covers the common column types; logical (`L`), bit (`X`), complex (`C`,
`M`) and variable-length (`P`, `Q`) columns would need a few more cases.

### VDIF frame

VDIF is the standard format for VLBI and pulsar baseband data. A frame header is
four little-endian 32-bit words of bit fields (and four more of extended data,
unless the legacy bit is set), so each word is a `BitStruct` with
`bitorder="little"`, its first field in the lowest bits. The time is a count of
seconds since a reference epoch, given in half-years since 2000. 2-bit samples
are packed with the oldest in the lowest bits, which is `bitorder="little"` again.

```python
from datetime import datetime, timedelta, timezone

def word(fields):
    return pb.BitStruct(fields, bitorder="little")

header = pb.Spec(
    {
        "w0": word({"seconds": pb.BitInt(30), "legacy": pb.BitFlag(), "invalid": pb.BitFlag()}),
        "w1": word({"frame": pb.BitInt(24), "epoch": pb.BitInt(6), "unassigned": pb.BitPadding(2)}),
        "w2": word({"length": pb.BitInt(24), "log2nchan": pb.BitInt(5), "version": pb.BitInt(3)}),
        "w3": word(
            {
                "station": pb.BitInt(16),
                "thread": pb.BitInt(10),
                "bitsm1": pb.BitInt(5),  # bits per sample, minus 1
                "complex": pb.BitFlag(),
            }
        ),
        "extended": pb.If(this.w0.legacy == 0, pb.Bytes(16)),
    }
)

def start(ctx):
    epoch = ctx.header.w1.epoch
    origin = datetime(2000 + epoch // 2, 1 + 6 * (epoch % 2), 1, tzinfo=timezone.utc)
    return origin + timedelta(seconds=ctx.header.w0.seconds)

frame = pb.Spec(
    {
        "header": header,
        "time": pb.Computed(start),
        "samples": pb.Array(
            pb.u8,
            # The frame length is in units of 8 bytes and includes the header.
            count=lambda ctx: 4 * (8 * ctx.header.w2.length - header.sizeof(ctx.header)),
            packing=2,
            bitorder="little",
        ),
    }
)

frames = pb.Greedy(frame).parse("scan.vdif")
```

This reads single-channel, 2-bit real data. The samples are offset binary: `0` is
the most negative level and `3` the most positive.

### Mark 5B frame

Mark 5B, the format VDIF replaced, has a 16-byte header of little-endian words:
a sync word, a word of bit fields, and the time as binary-coded decimal (BCD)
digits, one per 4 bits, which `Adapted` turns into an int. The day is the
Modified Julian Date (MJD) modulo 1000, so the thousands have to come from
elsewhere, such as the date of the observation.

```python
def bcd(wraps):
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

frame = mark5b.parse(raw)
mjd = 60000 + frame.jjjsssss // 100000
seconds = frame.jjjsssss % 100000 + frame.fraction / 10000
```

### PSRDADA file

A PSRDADA file starts with a text header of `KEY value` lines, padded with NULs
to `HDR_SIZE` bytes. `HDR_SIZE` is one of the keys, so it is read first with
`Peek`, which doesn't move the stream, and then the whole block is read.

```python
def parse(text):
    pairs = (line.split("#")[0].split(None, 1) for line in text.splitlines())
    return {pair[0]: pair[1].strip() for pair in pairs if len(pair) == 2}

def format(header):
    return "".join(f"{key} {value}\n" for key, value in header.items())

dada = pb.Spec(
    {
        "size": pb.Peek(
            pb.Adapted(pb.CString("ascii"), lambda t: int(parse(t)["HDR_SIZE"]), str)
        ),
        "header": pb.Adapted(pb.PaddedString(this.size, "ascii"), parse, format),
        "data": pb.Array(pb.i8),
    }
)

obs = dada.parse("2024-03-01-21:00:00_0000000000000000.000000.dada")
obs.header["SOURCE"], float(obs.header["TSAMP"])    # TSAMP is in microseconds
```

The values are text: convert the ones you need. How the samples are ordered
(by time, polarization and channel) depends on the instrument.

### SPICE ephemeris (DAF)

NASA's SPICE kernels, such as the JPL planetary ephemerides (`de440.bsp`), are
DAF files of 1024-byte records. The first record says whether the file is
little- or big-endian, but only 88 bytes in, after numbers that depend on it, so
a `Pointer` reads it first and a `Switch` picks the byte order. Two more
`Pointer`s follow the record numbers to the first summary record, which lists
what the file holds, and to the record of names after it.

```python
summary = pb.Spec(
    {
        "start": pb.f64,  # TDB seconds past J2000
        "stop": pb.f64,
        "target": pb.i32,  # NAIF ID codes, such as 399 for the Earth
        "center": pb.i32,
        "frame": pb.i32,
        "type": pb.i32,
        "begin": pb.i32,  # 1-based addresses of 8-byte words
        "end": pb.i32,
    }
)

def body(endian):
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
            "ftp": pb.Const(b"FTPSTR:\r:\n:\r\n:\r\x00:\x81:\x10\xce:ENDFTP", pb.Bytes(28)),
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

daf = pb.Spec(
    {
        "id": pb.PaddedString(8, "ascii", pad=" "),  # "DAF/SPK"
        "format": pb.Peek(pb.Pointer(88, pb.PaddedString(8, "ascii"))),
        "body": pb.Switch(this.format, {"LTL-IEEE": body("little"), "BIG-IEEE": body("big")}),
    }
)

kernel = daf.parse("de440.bsp")
[(s.target, s.center) for s in kernel.body.record.summaries]
```

This reads the first summary record of an SPK file (where each summary has 2
doubles and 6 integers). Larger files chain more summary records through `next`.

### SER video

SER files hold video from the cameras used for planetary and lunar imaging. A
178-byte little-endian header is followed by the frames and an optional trailer
with the time of each frame. Times are .NET ticks (100 ns since the year 1), of
which only the low 62 bits are used; `Timestamp` counts in microseconds here.

```python
from datetime import datetime

ticks = pb.Timestamp(
    pb.Adapted(pb.i64, lambda t: (t & (2**62 - 1)) // 10, lambda us: us * 10),
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
        "frames": pb.Repeat(pb.Array(pb.u16, count=this.width * this.height), this.nframes),
        "times": pb.Optional(pb.Repeat(ticks, this.nframes)),
    },
    endian="little",
)

video = ser.parse("jupiter.ser")
video.frames[0].reshape(video.height, video.width)
```

This reads 16-bit mono video, little-endian. (The `littleendian` flag should say
which byte order the frames use, but many programs write it with the opposite
meaning, so it is best not trusted.) For 8-bit video, use `pb.u8`; for colour,
multiply the count by 3.

### CCSDS space packets

Spacecraft send their data down as CCSDS space packets. The 6-byte header is bit
fields, followed by the length of the data minus one, which `Rebuild` fills in.

```python
packet = pb.Spec(
    {
        "header": pb.BitStruct(
            {
                "version": pb.BitInt(3),
                "type": pb.BitInt(1),  # 0 for telemetry, 1 for commands
                "secondary": pb.BitFlag(),  # whether a secondary header follows
                "apid": pb.BitInt(11),  # the application (instrument) ID
                "sequence": pb.BitInt(2),
                "count": pb.BitInt(14),
            }
        ),
        "length": pb.Rebuild(pb.u16, lenof(this.data) - 1),
        "data": pb.Bytes(this.length + 1),
    },
    endian="big",
)

packets = pb.Greedy(packet).parse("telemetry.bin")
```
