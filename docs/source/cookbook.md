# Cookbook

Real formats, written with pabo. Each of these is also in pabo's test suite.

## PNG header

```python
import pabo as pb
from pabo import this

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
        "byte_rate": pb.Rebuild(pb.u32, this.rate * this.channels * this.bits // 8),
        "block_align": pb.Rebuild(pb.u16, this.channels * this.bits // 8),
        "bits": pb.u16,
    }
)
samples = pb.Spec({"samples": pb.Array(pb.i16, count=this.size // 2)})

wav = pb.Spec(
    {
        "riff": pb.Const(b"RIFF", pb.Bytes(4)),
        "size": pb.Rebuild(pb.u32, 36 + 2 * pb.lenof(this.data.samples)),
        "wave": pb.Const(b"WAVE", pb.Bytes(4)),
        "fmt": chunk(b"fmt ", fmt, lambda ctx: 16),
        "data": chunk(b"data", samples, 2 * pb.lenof(this.samples)),
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
        "options": pb.Bytes((this.vihl.ihl - 5) * 4),
    },
    endian="big",
)
```
