# Tutorial

## Installation

```bash
pip install pabo
```

pabo needs Python 3.10 or later, and depends only on numpy and beartype.

## Constructs

A **construct** describes one piece of binary data. Every construct can
`parse` and `build`:

```python
import pabo as pb

u16 = pb.Int(2, endian="big")
u16.parse(b"\x01\x02")    # 258
u16.build(258)            # b'\x01\x02'
u16.size                  # 2
```

`parse` accepts `bytes` (or `bytearray`/`memoryview`), a path to a file, or any
readable binary stream. `build` returns bytes, or writes to a path or a writable
stream if you give one:

```python
u16.build(258, "out.bin")                 # overwrite out.bin
u16.build(259, "out.bin", append=True)    # append to it
```

Files given by path are memory-mapped, so large arrays are read without copying.

## Numbers

| Construct | Description |
| --- | --- |
| `Int(width, signed=False, endian=None)` | An integer of any number of bytes. |
| `Float(width, endian=None)` | A 2, 4 or 8-byte float. |
| `VarInt()`, `ZigZag()` | Variable-length integers (LEB128), unsigned and signed. |
| `Array(dtype, count=-1, packing=None, bitorder="big")` | A numpy array. |

`endian` is `"little"`, `"big"` or `"native"`. If you leave it out, the number
takes the endianness of the enclosing specification, or little-endian if there
is none. There are short aliases for common numbers: `pb.u8`, `pb.u16be`,
`pb.i32le`, `pb.f64`, and so on. The ones without a suffix (`pb.u32`) take the
endianness of the enclosing specification.

An `Array` with a negative `count` (the default) reads to the end of the stream.
With `packing`, each element is stored in that many bits (1, 2 and 4 bits use a
fast C++ extension; other widths work too):

```python
nibbles = pb.Array(pb.u8, count=4, packing=4)
nibbles.parse(b"\x12\x34")    # array([1, 2, 3, 4], dtype=uint8)
```

## Bytes, strings and flags

| Construct | Description |
| --- | --- |
| `Bytes(count)` | `count` raw bytes (all the rest, if negative). |
| `GreedyBytes()` | All the bytes up to the end of the stream. |
| `Flag()` | One byte, as a boolean. |
| `Padding(size)` | `size` null bytes. |
| `CString(code="utf-8")` | A null-terminated string. |
| `PascalString(pre, code="utf-8")` | A string prefixed by its length in bytes. |
| `PaddedString(length, code="utf-8", pad="\x00", side="right")` | A fixed-length padded string. |
| `GreedyString(code="utf-8")` | A string running to the end of the stream. |
| `Line(code="utf-8")` | A string ending in CRLF. |

## Specifications

A `Specification` (or `Spec`) is an ordered set of named fields. It parses into a
`Container`, which is a `dict` whose keys are also attributes:

```python
header = pb.Spec(
    {
        "magic": pb.Const(b"PB", pb.Bytes(2)),
        "version": pb.u8,
        "count": pb.u16,
    },
    endian="big",
)

data = header.parse(b"PB\x01\x00\x03")
data.count                                    # 3
data == {"magic": b"PB", "version": 1, "count": 3}   # True
header.build({"version": 1, "count": 3})      # b'PB\x01\x00\x03'
```

`Const` values can be left out when building, and they are checked when
parsing. Specifications nest, and `Embedded` puts the fields of one specification
straight into another.

## Fields that depend on other fields

Most real formats store a length or a type before the data it describes. Refer to
an earlier field with `this`:

```python
from pabo import this

message = pb.Spec(
    {
        "length": pb.u8,
        "payload": pb.Bytes(this.length),
    }
)
message.parse(b"\x03abc")    # Container({'length': 3, 'payload': b'abc'})
```

`this._.name` refers to a field of the enclosing specification. For anything more
than a plain reference, pass a function of the context: `lambda ctx: ctx.n * 2`.
(Comparisons such as `this.n == 0` don't build expressions, so write
`lambda ctx: ctx.n == 0`.)

When building, `Rebuild` computes a field from the others, so you don't have to
fill in lengths yourself:

```python
message = pb.Spec(
    {
        "length": pb.Rebuild(pb.u8, lambda ctx: len(ctx.payload)),
        "payload": pb.Bytes(this.length),
    }
)
message.build({"payload": b"abc"})    # b'\x03abc'
```

`Computed` adds a field that takes no bytes, such as an area computed from a width
and a height.

## Control flow

| Construct | Description |
| --- | --- |
| `If(cond, then, otherwise=None)` | Choose a construct by a condition. |
| `Switch(key, cases, default=None)` | Choose a construct by a key (a tagged union). |
| `Optional(wraps)` | Parse if possible, else rewind and give None. |
| `Repeat(wraps, count)` | Repeat a fixed (or context-dependent) number of times. |
| `RepeatUntil(predicate, wraps)` | Repeat until `predicate(element, ctx)` holds. |
| `Greedy(wraps)` | Repeat until parsing fails. |
| `StopIf(cond)` | End the enclosing specification early. |
| `Terminated()` | Check that the stream has ended. |
| `Check(func)`, `Validated(wraps, predicate)` | Validate values. |

```python
record = pb.Spec(
    {
        "kind": pb.u8,
        "body": pb.Switch(
            this.kind,
            {1: pb.u32, 2: pb.CString()},
        ),
    }
)
record.parse(b"\x02hello\x00")    # Container({'kind': 2, 'body': 'hello'})
```

## Bit fields

`BitStruct` packs named fields narrower than a byte:

```python
ip_first_byte = pb.BitStruct({"version": pb.BitInt(4), "ihl": pb.BitInt(4)})
ip_first_byte.parse(b"\x45")    # Container({'version': 4, 'ihl': 5})
```

`BitFlag` is a single bit as a boolean, and `BitPadding` skips bits.

## Moving around the stream

`Seek`, `Tell`, `Pointer` (parse at an offset and come back), `Peek` (look ahead),
`Aligned` and `AlignedSpec` (pad to a multiple of some bytes), and `Lazy` (skip a
field and parse it when asked for) handle formats with offsets and alignment.

## Transforms and adapters

`Compressed` (zlib, gzip, bz2, lzma), `Transformed` (any bytes-to-bytes encoding),
and `Checksummed` (CRC32, Adler-32, any hashlib digest, or your own function) deal
with encoded data. `Enum`, `FlagsEnum`, `Timestamp` (Unix, MJD or your own epoch)
and `Adapted` turn raw values into richer Python objects.

## Class-based specifications

Subclass `Struct` to parse into typed dataclass instances:

```python
class PNGHeader(pb.Struct, endian="big"):
    magic: bytes = pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8))
    ihdr_size: int = pb.u32
    ihdr_id: bytes = pb.Const(b"IHDR", pb.Bytes(4))
    width: int = pb.u32
    height: int = pb.u32

header = PNGHeader.parse("example.png")
header.width
PNGHeader(ihdr_size=13, width=602, height=172).build()
```

## Debugging

Errors say which field failed and where:

```text
pabo.errors.StreamError: 바보! STREAM ENDED EARLY: EXPECTED 2 BYTES, GOT 1. (AT header.sizes[2], OFFSET 7) ABORT.
```

All errors are subclasses of `PaboError`: `StreamError`, `SizeofError`,
`ValidationError` (with `ConstError`) and `ContextError`. Also:

- `spec.describe()` prints a table of offsets, sizes, types and docs.
- `spec.parse(data, trace=True)` prints every field as it is parsed, with a hex
  dump of its bytes.
- `Probe()` prints the context and the next few bytes wherever you put it.
- `construct / "some docs"` attaches docs to a field; they show up in errors and
  in `describe()`.

## Performance

Specifications made only of fixed-size numbers, bytes and constants are compiled
into a single `struct` call, and repeats of them are parsed in bulk. Arrays are read
straight into numpy, without copies when parsing a file. Runtime type checking of
pabo's own functions (by beartype) can be turned off with the environment variable
`PABO_BEARTYPE=0`.
