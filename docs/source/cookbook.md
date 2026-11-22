# Cookbook

Real formats, written with pabo. Each of these is also in pabo's test suite.

## PNG header

```python
import pabo as pb

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

## WAV (RIFF) audio

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
        "byte_rate": pb.Rebuild(pb.u32, lambda ctx: ctx.rate * ctx.channels * ctx.bits // 8),
        "block_align": pb.Rebuild(pb.u16, lambda ctx: ctx.channels * ctx.bits // 8),
        "bits": pb.u16,
    }
)
samples = pb.Spec({"samples": pb.Array(pb.i16, count=lambda ctx: ctx.size // 2)})

wav = pb.Spec(
    {
        "riff": pb.Const(b"RIFF", pb.Bytes(4)),
        "size": pb.Rebuild(pb.u32, lambda ctx: 36 + 2 * len(ctx.data.samples)),
        "wave": pb.Const(b"WAVE", pb.Bytes(4)),
        "fmt": chunk(b"fmt ", fmt, lambda ctx: 16),
        "data": chunk(b"data", samples, lambda ctx: 2 * len(ctx.samples)),
        "end": pb.Terminated(),
    },
    endian="little",
)

audio = wav.parse("tone.wav")
audio.fmt.rate, audio.data.samples
```

## ELF header

The endianness of an ELF file is given by a byte in its header, and the size of
its addresses by another. `Switch` picks a body with the right endianness, and
`If` picks the address size.

```python
def body(endian):
    is64 = lambda ctx: ctx._.ident.cls == 2
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
        "header": pb.Switch(lambda ctx: ctx.ident.data, {1: body("little"), 2: body("big")}),
    }
)

elf.parse("/bin/ls").header.machine
```

## SIGPROC filterbank header

SIGPROC headers, used for pulsar data, are a list of keyword/value pairs between
`HEADER_START` and `HEADER_END`. The type of each value depends on its keyword.

```python
key = pb.PascalString(pb.i32)
entry = pb.Spec(
    {
        "key": key,
        "value": pb.Switch(
            pb.this.key,
            {
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
            },
        ),
    }
)
header = pb.Spec(
    {
        "start": pb.Const("HEADER_START", key),
        "entries": pb.RepeatUntil(lambda e, ctx: e.key == "HEADER_END", entry),
        "meta": pb.Computed(lambda ctx: {e.key: e.value for e in ctx.entries}),
    },
    endian="little",
)
```

The data that follows can then be read as a (possibly bit-packed) `Array`, which
is memory-mapped and read without copying when parsing a file.

## IPv4 header

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
        "options": pb.Bytes(lambda ctx: (ctx.vihl.ihl - 5) * 4),
    },
    endian="big",
)
```
