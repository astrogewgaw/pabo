# Comparison with other libraries

There are many libraries for binary data in Python. They fall into a few kinds:

- **Declarative libraries**, where you describe a layout once and use it to parse
  and build: [construct](https://github.com/construct/construct),
  [structures](https://github.com/malinoff/structures),
  [pystructs](https://github.com/moreal/pystructs),
  [duckparse](https://github.com/i64/duckparse) and pabo.
- **Fixed layouts**, close to `struct`: [binmap](https://github.com/HeMan/binmap)
  and [dataclasses-struct](https://github.com/harrymander/dataclasses-struct)
  map a dataclass onto one `struct` format, and
  [bitstruct](https://github.com/eerimoq/bitstruct) unpacks format strings at the
  bit level, in C.
- **Other description languages**:
  [dissect.cstruct](https://github.com/fox-it/dissect.cstruct) reads C struct
  declarations, and [Kaitai Struct](https://kaitai.io) compiles YAML (`.ksy`)
  descriptions into parsers for many languages.
- **Bit-level layouts**: [bread](https://github.com/alexras/bread) addresses
  every field in bits.

pabo is a declarative library, in the line of construct, with large numeric
arrays (and bit-packed ones) as first-class data, since its main use is reading
astronomical data. See [](performance.md) for how fast each one parses.

## At a glance

| | Style | Builds bytes | Fields from earlier fields | numpy arrays | Latest release |
| --- | --- | --- | --- | --- | --- |
| **pabo** | dicts of constructs, or dataclasses | yes | yes | yes, zero-copy | |
| construct | `"name" / Construct` | yes | yes | no | 2.10.70 (2023) |
| structures | class attributes | yes | yes | no | 0.9.5 (2018), needs a patch on Python 3.10+ |
| pystructs | class attributes, Django-style | yes | | no | 0.4.0 (2025), Python 3.13+ |
| duckparse | annotations, code generated with `exec` | no | | no | unreleased, last change 2020 |
| dissect.cstruct | C declarations | yes | yes | no | 4.7 (2025) |
| Kaitai Struct | `.ksy` files, compiled ahead of time | in 0.11, optionally | yes | no | 0.11 (2025) |
| binmap | dataclasses on one `struct` format | yes | no | no | 1.2.1 (2024) |
| dataclasses-struct | dataclasses on one `struct` format | yes | no | no | 1.5.2 (2026) |
| bitstruct | format strings, in C | yes | no | no | 8.24.0 (2026) |
| bread | lists of fields, addressed in bits | yes | | no | 3.1.0 (2018), archived |

(A blank means the library has some way of doing it that this page doesn't
describe.)

## What pabo does differently

- **Arrays are numpy arrays.** `Array` parses numbers into a numpy array, as a
  view of the bytes or memory-mapped file being parsed, so a million values take
  microseconds; values packed into 1, 2 or 4 bits are unpacked in C++. Every other
  library here returns a list of Python numbers.
- **Fixed-size parts are compiled automatically.** A specification of fixed-size
  fields becomes one `struct` call, and repeats of it are parsed in bulk, without
  a separate `compile()` step (construct), generated code (duckparse, Kaitai) or a
  C extension (bitstruct).
- **Plain Python, no new language.** Layouts are dicts of constructs, or
  dataclass-like classes. Fields that depend on others use `this.name`
  expressions or ordinary functions, not strings of code (duckparse, Kaitai) or
  C declarations (dissect.cstruct).
- **Errors say where.** Every error is a `PaboError` with the path of the field
  that failed, its offset and its docs, and `trace=True` and `describe()` show the
  layout as it is parsed.
- **Typed.** The public API is type-checked at runtime with beartype, and pabo
  ships `py.typed`.

## The libraries

**construct** is the most complete declarative library, and the one pabo is
modelled on. It has more constructs than pabo (such as `RawCopy`), and can
compile a layout into
Python code for speed. pabo has fewer, plainer constructs, numpy arrays, and
automatic compilation. [construct-typing](https://github.com/timrid/construct-typing)
adds type hints and dataclasses to it.

**structures** looks much like pabo's `Struct` classes, with constants, dependent
fields and bounded repeats. It has not been updated since 2018, and needs
`collections.Sequence` (removed in Python 3.10) to be patched back in.

**pystructs** declares fields as class attributes with an inner `Meta` class, and
has validators (`Range`, `OneOf`, `Regex`) and a check that no bytes are left over
after parsing. Its current version needs Python 3.13.

**duckparse** turns annotated classes into generated `__init__` methods. It only
parses, and repeat counts are written as strings of Python code. It has not
changed since 2020.

**dissect.cstruct** is the natural choice when you already have C headers: it
reads C struct, union, enum and bit field declarations, and compiles them for
speed. It is part of a maintained forensics toolkit.

**Kaitai Struct** describes formats in YAML and compiles them into parsers for a
dozen languages, with a web IDE and a large gallery of ready-made formats. It
needs a separate compiler, and its Python parsers read values one at a time.

**binmap** and **dataclasses-struct** turn a dataclass into one `struct` format,
which is simple and quick for fixed layouts, but has no repeats, nesting or fields
of variable size.

**bitstruct** packs and unpacks format strings such as `"u3s11f32"` at any bit
offset, in C, which makes it the fastest library here after `struct` itself.
It has no constants, repeats or dependent fields, and little-endian data has to
be byte-swapped first.

**bread** describes layouts as lists of fields addressed in bits, so fields of
any bit width can go anywhere. It is archived, slow, and needs patches to run on
Python 3.12.

Other libraries in the same space include
[cstruct](https://github.com/andreax79/python-cstruct) (C declarations, like
dissect.cstruct), [binobj](https://github.com/dargueta/binobj),
[structured-classes](https://github.com/lojack5/structured),
[pycstruct](https://github.com/midstar/pycstruct) and
[rawutil](https://github.com/Tyulis/rawutil); and
[hachoir](https://github.com/vstinner/hachoir), a collection of ready-made
parsers for file formats.

## Translating construct code

| construct | pabo |
| --- | --- |
| `Struct("a" / Int16ub, "b" / Bytes(this.a))` | `Spec({"a": pb.u16be, "b": pb.Bytes(this.a)})` |
| `Array(this.n, Int32sl)` | `pb.Array(pb.i32le, count=this.n)` (numpy) or `pb.Repeat(pb.i32le, this.n)` (list) |
| `PrefixedArray(Int8ub, Byte)` | `pb.Prefixed(pb.u8, pb.Array(pb.u8))` (the prefix is a length in bytes) |
| `PascalString(Int8ub, "utf8")` | `pb.PascalString(pb.u8)` |
| `CString("utf8")` | `pb.CString()` |
| `Const(b"MAGIC")` | `pb.Const(b"MAGIC", pb.Bytes(5))` |
| `Enum(Int8ub, a=1, b=2)` | `pb.Enum(pb.u8, MyEnum)` with a Python `enum.Enum` |
| `If(this.x, Int8ub)` | `pb.If(this.x, pb.u8)` |
| `Switch(this.t, {...})` | `pb.Switch(this.t, {...})` |
| `RepeatUntil(lambda x, lst, ctx: x == 0, Byte)` | `pb.RepeatUntil(lambda x, ctx: x == 0, pb.u8)` |
| `Computed(this.a * 2)` | `pb.Computed(this.a * 2)` |
| `Rebuild(Int8ub, len_(this.data))` | `pb.Rebuild(pb.u8, pb.lenof(this.data))` |
| `Pointer(8, Int8ub)` | `pb.Pointer(8, pb.u8)` |
| `Checksum(...)` | `pb.Checksummed(wraps, check, "crc32")` |
| `Compressed(GreedyBytes, "zlib")` | `pb.Compressed(pb.GreedyBytes(), "zlib")` |
| `VarInt` | `pb.VarInt()` (and `pb.VarInt(order="big")` for MIDI-style numbers) |
| `Struct(...).compile()` | nothing to do: fixed-size specifications are compiled automatically |
