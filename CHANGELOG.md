# Changelog

All notable changes to pabo are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

This release is a rewrite. Code that defines its own constructs needs updating
(see "Changed").

### Added

- Fields that depend on other fields: `this.name`, `this._.name`, or any
  function of the context, accepted wherever a count, length, offset or
  condition is expected.
- Control flow: `Computed`, `Rebuild`, `If`, `Optional`, `Switch`,
  `RepeatUntil`, `StopIf`, `Terminated`, `Check` and `Validated`.
- Numbers: integers of any width (`Int(3)`, `Int(16)`), half floats
  (`Float(2)`), `VarInt` and `ZigZag`, `"native"` endianness, a default
  endianness per specification, and short aliases (`u8`, `u16be`, `i32le`,
  `f64`, ...).
- `Enum`, `FlagsEnum` and `Timestamp` (Unix, MJD or any epoch).
- `GreedyBytes`, `GreedyString`, and a configurable pad character and side for
  `Padded` and `PaddedString`.
- `BitStruct` with `BitInt`, `BitFlag` and `BitPadding`, and bit packing of any
  width in `Array` (1, 2 and 4 bits use the C++ extension).
- Stream positioning: `Seek`, `Tell`, `Pointer`, `Peek`, `Aligned`,
  `AlignedSpec` and `Lazy`.
- `Transformed`, `Compressed` (zlib, gzip, bz2, lzma) and `Checksummed`.
- Class-based specifications with `Struct`, which parse into dataclasses.
- `Embedded`, to merge one specification into another.
- Results are `Container`s: dicts whose keys are also attributes.
- Errors say which field failed (`header.sizes[2]`), at what offset, and give
  the field's docs. There is a hierarchy of errors under `PaboError`:
  `StreamError`, `SizeofError`, `ValidationError`, `ConstError` and
  `ContextError`.
- `describe()`, `parse(..., trace=True)` and `Probe` for debugging, and
  `sizeof(ctx)` for sizes that depend on the data.
- Files are memory-mapped when parsed from a path, and arrays parsed from them
  are zero-copy views.
- `pabo.__version__`, `py.typed`, and a type stub for the C++ extension.
- Strict type hints (`pabo.hints`) on every construct and public function, so
  beartype rejects bad arguments as soon as a construct is created.
- `Timestamp` units: "s", "ms", "us", "ns" or "day".
- A test suite (with hypothesis), benchmarks, CI, and documentation.

### Changed

- All error messages are in uppercase.
- Functions no longer have underscores in their names: `readexact`,
  `packbits`/`unpackbits`, `todict`/`fromdict`, `formatfor`, `dtypefor`.

- The construct hooks are now `_size(ctx)`, `_parse(stream, ctx)` and
  `_build(data, stream, ctx)`, and `_build` returns the value it wrote.
- `Int`, `Float` and specifications default to inheriting their endianness
  (little-endian at the top level).
- `construct / "docs"` returns a copy instead of changing the construct.
- Specifications made of fixed-size fields are compiled into a single `struct`
  call, and repeats of them are parsed in bulk.
- Runtime type checking can be turned off with `PABO_BEARTYPE=0`.
- The build moved to scikit-build-core and nanobind. Releases use trusted
  publishing.

### Fixed

- Many correctness bugs; see `TODO.md` for the full list.
