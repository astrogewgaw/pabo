# Changelog

All notable changes to pabo are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

This release is a rewrite. Code that defines its own constructs needs updating
(see "Changed").

### Added

- Parameters: keyword arguments to `parse` and `build`, read by fields as
  `this._params.name`, and `parse(..., strict=True)`, which rejects bytes left
  over after the data.
- `Default`, for fields that can be left out when building, and
  `Rebuild(..., check=True)`, to check computed fields when parsing.
- The elements of `Repeat`, `RepeatUntil` and `Greedy` can read their
  position as `this._index`, and `Greedy` takes a minimum and maximum count.
- Fields that depend on other fields: `this.name`, `this._.name`, expressions
  such as `this.n * 2`, `this.kind == 3` or `lenof(this.data)`, or any function
  of the context, accepted wherever a count, length, offset or condition is
  expected.
- Control flow: `Computed`, `Rebuild`, `If`, `Optional`, `Switch`, `Select`,
  `Union`, `Deferred`, `RepeatUntil`, `StopIf`, `Terminated`, `Check` and
  `Validated`.
- Numbers: integers of any width (`Int(3)`, `Int(16)`), half floats
  (`Float(2)`), `VarInt` (LEB128, or most significant first with
  `order="big"`, as in MIDI) and `ZigZag`, `"native"` endianness, a default
  endianness per specification, and short aliases (`u8`, `u16be`, `i32le`,
  `f64`, ...).
- `Enum` (which can keep unknown values with `strict=False`), `FlagsEnum` and
  `Timestamp` (Unix, MJD, Windows FILETIME, .NET ticks or any epoch).
- `Array` of a fixed-size specification, which parses into a numpy structured
  array (a view of the data, like other arrays).
- `GreedyBytes`, `GreedyString`, and a configurable pad character and side for
  `Padded` and `PaddedString`.
- `Delimited`, for bytes, strings or anything else ending in a terminator of
  any length (with options to keep it, leave it in the stream, or accept the
  end of the stream instead).
- `FixedSized`, to parse a construct inside a window of a given number of
  bytes (padding it when building), and `Remaining`, for the rest of the
  stream except a trailer of a given size.
- `BitStruct` with `BitInt`, `BitFlag` and `BitPadding` (fields of any number
  of bits), and a `bitorder` option for bit-packed `Array`s, which support 1, 2
  and 4 bits per value (other widths raise an error).
- Stream positioning: `Seek`, `Tell`, `Pointer`, `Peek`, `Aligned`,
  `AlignedSpec` and `Lazy`.
- `Transformed`, `Compressed` (zlib, gzip, bz2, lzma) and `Checksummed` (with
  the checksum after or before the data).
- Class-based specifications with `Struct`, which parse into dataclasses.
- `Embedded`, to merge one specification into another.
- Results are `Container`s: dicts whose keys are also attributes.
- Errors say which field failed (`header.sizes[2]`), at what offset, and give
  the field's docs. There is a hierarchy of errors under `PaboError`:
  `StreamError`, `SizeofError`, `ValidationError`, `ConstError` and
  `ContextError`. Exceptions raised by your own functions (`Adapted`'s decode
  and encode, predicates, checksum functions, functions of the context) are
  turned into these too, so `Greedy` stops on them and they carry the path.
- Docs attached with `/` are shown in `repr`, error messages and `describe()`.
- `describe()`, `dump()` (a hex dump with the fields marked),
  `parse(..., trace=True)`, `parse(..., offsets=True)` (which records where
  each field was) and `Probe` for debugging, and
  `sizeof(ctx)` for sizes that depend on the data.
- Arrays are parsed without copying, like `np.frombuffer`: from bytes (or a
  `bytearray` or `memoryview`) they are read-only views of them, and files
  parsed from a path are memory-mapped and viewed in the same way.
- `pabo.__version__`, `py.typed`, and a type stub for the C++ extension.
- Strict type hints (`pabo.hints`) on every construct and public function, so
  beartype rejects bad arguments as soon as a construct is created.
- `Timestamp` units: "s", "ms", "us", "ns" or "day".
- A test suite (with hypothesis), benchmarks, CI, and documentation, including
  a "Performance" page with plots of the benchmark results. The documentation
  moves from Read the Docs to GitHub Pages: https://astrogewgaw.github.io/pabo/.

### Changed

- All error messages are in uppercase.
- Functions no longer have underscores in their names: `readexact`,
  `packbits`/`unpackbits`, `todict`/`fromdict`, `formatfor`, `dtypefor`.

- The construct hooks are now `_size(ctx)`, `_parse(stream, ctx)` and
  `_build(data, stream, ctx)`, and `_build` returns the value it wrote.
- `Int`, `Float` and specifications default to inheriting their endianness
  (little-endian at the top level).
- `construct / "docs"` returns a copy instead of changing the construct.
- Fields whose names start with an underscore are left out of parsed results
  (and of `Struct` dataclasses), for padding and reserved bytes.
- Specifications made of fixed-size fields are compiled into a single `struct`
  call, and repeats of them (including class-based `Struct`s) are parsed and
  built in bulk.
- Runtime type checking can be turned off with `PABOROAR=0`.
- The build moved to scikit-build-core and nanobind. Releases use trusted
  publishing.

### Fixed

- Building into an open file silently did nothing (`isinstance(src, BinaryIO)` is
  never true for real files), and building to a path appended instead of
  overwriting. Paths are now overwritten unless `append=True`.
- `parse` now accepts `bytearray` and `memoryview` as well as `bytes`.
- `Array.size` was the element count rather than the size in bytes, and packed
  arrays read the wrong number of bytes, accepted any dtype, and did not check
  greedy reads.
- `Bits.size` was in bits, and counts that were not a multiple of 8 lost bits.
- `Int`/`Float` with an unsupported width failed with a cryptic `struct.error`,
  and any `endian` other than `"big"` silently meant little-endian.
- `Flag` parsed `True` at the end of the stream; `Bytes` did not check lengths.
- `Line` never found its CRLF; `CString` failed for UTF-16 and UTF-32;
  `PaddedString` accepted strings that were too long; `Padded` stripped null
  bytes that belonged to the payload.
- `Greedy.size` returned a method, and `Greedy` crashed at the end of the stream
  instead of stopping, without rewinding after a partial element.
- `Sequential` silently truncated on a length mismatch and ignored
  variable-size members in `size`, and `Prefixed.size` was meaningless.
- Constants and padding had to be given a value when building a specification.
- The C++ extension had a data race with OpenMP (which was never actually
  enabled), silently dropped elements that did not fill a byte, did not mask
  values wider than `nbits`, and did not build on Windows.
