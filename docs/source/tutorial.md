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

Bytes left over after the data are ignored, unless you pass `strict=True`. Files
given by path are memory-mapped. Either way, large arrays are not copied:
like `np.frombuffer`, `parse` returns read-only views of the bytes or the file
(call `.copy()` for an array you can change).

## Numbers

| Construct | Description |
| --- | --- |
| `Int(width, signed=False, endian=None)` | An integer of any number of bytes. |
| `Float(width, endian=None)` | A 2, 4 or 8-byte float. |
| `VarInt(order="little")`, `ZigZag()` | Variable-length integers, unsigned (LEB128, or most significant first with `order="big"`, as in MIDI) and signed. |
| `Array(dtype, count=-1, packing=None, bitorder="big")` | A numpy array of numbers, or of records. |

`endian` is `"little"`, `"big"` or `"native"`. If you leave it out, the number
takes the endianness of the enclosing specification, or little-endian if there
is none. There are short aliases for common numbers: `pb.u8`, `pb.u16be`,
`pb.i32le`, `pb.f64`, and so on. The ones without a suffix (`pb.u32`) take the
endianness of the enclosing specification.

An `Array` with a negative `count` (the default) reads to the end of the stream.
With `packing`, each element is stored in 1, 2 or 4 bits, unpacked by a fast
C++ extension (other widths raise an error):

```python
nibbles = pb.Array(pb.u8, count=4, packing=4)
nibbles.parse(b"\x12\x34")    # array([1, 2, 3, 4], dtype=uint8)
```

The elements can also be records: a specification made only of fixed-size
numbers, bytes, flags and constants gives a numpy structured array, with a named
field for each of its fields. This is much faster than a `Repeat`, which makes a
dict per record:

```python
point = pb.Spec({"x": pb.f32, "y": pb.f32, "id": pb.u16})
points = pb.Array(point, count=1000).parse(raw)
points["x"].mean(), points[0]["id"]
```

## Bytes, strings and flags

| Construct | Description |
| --- | --- |
| `Bytes(count)` | `count` raw bytes (all the rest, if negative). |
| `GreedyBytes()` | All the bytes up to the end of the stream. |
| `Flag()` | One byte, as a boolean. |
| `Padding(size)` | `size` null bytes. |
| `CString(code="utf-8")` | A null-terminated string. |
| `PascalString(pre, code="utf-8")` | A string prefixed by its length in bytes (`pre` is `pb.u8`, `pb.VarInt()`, ...). |
| `PaddedString(length, code="utf-8", pad="\x00", side="right")` | A fixed-length padded string. |
| `GreedyString(code="utf-8")` | A string running to the end of the stream. |
| `Line(code="utf-8")` | A string ending in CRLF. |
| `Delimited(wraps, term=b"\x00", include=False, consume=True, eos=False)` | `wraps`, ending at the first `term`, e.g. `Delimited(GreedyString(), term=b";")`. |

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

Fields whose names start with an underscore, such as `"_reserved": pb.Padding(4)`,
are parsed and built as usual (and later fields can refer to them), but are left
out of the result. `Const` values can be left out when building, and they are
checked when parsing. Fields wrapped in `Default(construct, value)` can be left out too, and
are built with `value` (or `value(ctx)`, if it is a function). Specifications nest, and `Embedded` puts the fields of one specification
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

`this._.name` refers to a field of the enclosing specification, `this._root.name`
to one at the top level, and `this._index` to the position of the element being
parsed in a `Repeat`, `RepeatUntil` or `Greedy`. References combine into **expressions**, evaluated when
the field is parsed or built: arithmetic (`this.n * 2`), bitwise operators
(`this.flags & 0x80`), comparisons (`this.kind == 3`), indexing (`this.items[0]`)
and `lenof(this.data)` all work.

Python's `and`, `or` and `not` can't be overloaded, so use `&` and `|` with
parentheses around each comparison, `(this.a == 1) & (this.b == 2)`, and `== 0`
for "not". Using an expression where Python needs a plain `True`/`False` raises
an error that says so. For anything else, pass a function of the context:
`lambda ctx: ctx.a == 1 and ctx.b == 2`. Both work wherever a count, length,
offset or condition is expected.

When building, `Rebuild` computes a field from the others, so you don't have to
fill in lengths yourself:

```python
message = pb.Spec(
    {
        "length": pb.Rebuild(pb.u8, pb.lenof(this.payload)),
        "payload": pb.Bytes(this.length),
    }
)
message.build({"payload": b"abc"})    # b'\x03abc'
```

With `Rebuild(..., check=True)`, parsing also checks that the stored value is the
one it would be built as (once the fields after it have been parsed), so a wrong
length raises an error.

`Computed` adds a field that takes no bytes, such as an area computed from a width
and a height.

Values that the data depends on but doesn't contain, such as a number of channels
known from another file, can be passed to `parse` and `build` as keyword
arguments, and read as `this._params.name`:

```python
frame = pb.Spec({"samples": pb.Array(pb.u8, count=this._params.nchans)})
frame.parse(raw, nchans=64)
```

## Control flow

| Construct | Description |
| --- | --- |
| `If(cond, then, otherwise=None)` | Choose a construct by a condition. |
| `Switch(key, cases, default=None)` | Choose a construct by a key (a tagged union). |
| `Select([a, b, ...])` | The first alternative that parses. |
| `Union({"name": construct, ...})` | Several views of the same bytes. |
| `Deferred(func)` | The construct `func(ctx)` returns: for layouts that depend on earlier data, or contain themselves. |
| `Optional(wraps)` | Parse if possible, else rewind and give None. |
| `Repeat(wraps, count)` | Repeat a fixed (or context-dependent) number of times. |
| `RepeatUntil(predicate, wraps)` | Repeat until `predicate(element, ctx)` holds. |
| `Greedy(wraps, minimum=0, maximum=None)` | Repeat until parsing fails (or `maximum` is reached). |
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

`Seek`, `Tell`, `Pointer` (parse at an offset, from the start, the current
position or the end, and come back), `Peek` (look ahead), `Remaining` (the rest
of the stream, except a trailer of so many bytes), `Aligned` and `AlignedSpec`
(pad to a multiple of some bytes), `FixedSized` (parse inside a window of so many
bytes, skipping what isn't used), and `Lazy` (skip a field and parse it when
asked for) handle formats with offsets and alignment.

## Transforms and adapters

`Compressed` (zlib, gzip, bz2, lzma), `Transformed` (any bytes-to-bytes encoding),
and `Checksummed` (CRC32, Adler-32, any hashlib digest, or your own function,
stored after the data or, with `first=True`, before it) deal with encoded data.
`Enum` (with `strict=False`, unknown values are kept as plain ints), `FlagsEnum`,
`Timestamp` (Unix, MJD, Windows, .NET or your own epoch) and `Adapted` turn raw
values into richer Python objects.

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
- `spec.parse(data, offsets=True)` gives every parsed specification an `_offsets`
  attribute: the (start, end) offsets of each of its fields.
- `print(spec.dump(data, color=True))` shows a hex dump with each field's bytes
  in its own colour, and the fields named at the end of each line.
- `Probe()` prints the context and the next few bytes wherever you put it, and
  `Debug(construct)` opens the Python debugger where `construct` fails.
- `construct / "some docs"` attaches docs to a field; they show up in errors, in
  `describe()` and in the construct's `repr`.

## Performance

Specifications made only of fixed-size numbers, bytes and constants are compiled
into a single `struct` call, and repeats of them are parsed in bulk. Arrays are
views of the bytes or file being parsed, as with `np.frombuffer`, and are read
straight into numpy from other streams. Runtime type checking of
pabo's own functions (by beartype) can be turned off with the environment variable
`PABOROAR=0`.
