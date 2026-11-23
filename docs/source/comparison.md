# pabo and construct

pabo is inspired by [construct](https://github.com/construct/construct), and covers
most of the same ground. The two differ mainly in how much magic they use.

| | construct | pabo |
| --- | --- | --- |
| Naming fields | `"width" / Int32ub` | `{"width": pb.u32be}`, or a `Struct` class |
| Expressions | `this.n * 2`, `this.n == 0` | `this.n`, or `lambda ctx: ctx.n * 2` |
| Results | `Container` | `Container` (a `dict`), or a dataclass with `Struct` |
| Default endianness | per field | per field, or per `Spec(..., endian=...)` |
| Large arrays | lists of Python objects | numpy arrays, zero-copy from memory-mapped files |
| Bit-packed data | `BitStruct`, `Bitwise` | `BitStruct`, and `Array(..., packing=n)` for 1, 2 or 4 bits, in C++ |
| Speed | interpreted, or `.compile()` | fixed-size specifications are compiled automatically |
| Errors | path in the message | path, offset and docs, plus `trace=True` and `describe()` |
| Type checking | none | public API checked at runtime with beartype, ships `py.typed` |

Some construct features pabo leaves out on purpose:

- **Expression objects.** `this.n * 2` is convenient, but it needs operator
  overloading on every expression, and comparisons like `this.n == 0` silently
  mean something else than in plain Python. pabo uses ordinary functions instead.
- **Embedding by magic.** pabo's `Embedded` is explicit, and only works on
  specifications.
- **Many near-duplicate constructs.** For example, pabo has one `Int` that takes
  any width, instead of `Int8ub`, `Int16sl`, `Int24ub`, ... (though the short
  aliases `u8`, `i16le`, `u24be`, ... are there if you like them).

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
| `Computed(this.a * 2)` | `pb.Computed(lambda ctx: ctx.a * 2)` |
| `Rebuild(Int8ub, len_(this.data))` | `pb.Rebuild(pb.u8, lambda ctx: len(ctx.data))` |
| `Pointer(8, Int8ub)` | `pb.Pointer(8, pb.u8)` |
| `Checksum(...)` | `pb.Checksummed(wraps, check, "crc32")` |
| `Compressed(GreedyBytes, "zlib")` | `pb.Compressed(pb.GreedyBytes(), "zlib")` |
