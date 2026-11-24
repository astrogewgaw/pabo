# TODO

Features and fixes found by comparing pabo with other binary parsing libraries
(construct, structures, pystructs, duckparse, dissect.cstruct, Kaitai Struct,
binmap, dataclasses-struct, bitstruct, bread) and by writing the cookbook. Each
item says where the idea comes from. Within each section, the most useful come
first.

## Performance

- [ ] **Structured arrays for fixed-size specifications**, such as
  `Array(record_spec, count=n)` returning a numpy structured array (a view, like
  `np.frombuffer`), for tables of records. Their `_Plan` already has the format.

## Constructs

- [ ] **Bytes and strings ending in any terminator**, not just a null (`CString`)
  or CRLF (`Line`), with options to keep or consume it. (Kaitai `terminator`,
  `include`, `consume`; construct `NullTerminated(term=...)`.)
- [ ] **A fixed-size window**, `FixedSized(length, wraps)`: parse `wraps` inside
  `length` bytes and skip what it doesn't use (C structs with reserved tails).
  `Padded` adds a number of bytes instead of padding to a total. (construct
  `FixedSized`, Kaitai `size:`.)
- [ ] **`Union`**: several views of the same bytes, moving on by the largest.
  And `Select`: the first of several alternatives that parses. (construct
  `Union`/`Select`, dissect.cstruct `union`.)
- [ ] **A construct chosen by a function of the context**, such as
  `Deferred(lambda ctx: rowspec(ctx.meta))`, so FITS tables can be read in one
  pass. With a function of nothing, it also gives recursive layouts. (construct
  `LazyBound`; found writing the FITS cookbook recipe.)
- [ ] **Data at the end of the stream**: negative offsets for `Pointer`/`Seek`
  (from the end, as in construct), and a way to read "everything except the last
  N bytes" that also builds. Needed for gzip trailers and the ZIP central
  directory. (construct `Pointer`; found writing the cookbook.)
- [ ] **Checksums over any earlier data**, not only a check that follows what it
  covers: for example, a checksum before the data, or over several fields. (construct
  `RawCopy` + `Checksum`, structures `Checksum`.)
- [ ] **Parameters passed to `parse`/`build`**, such as `spec.parse(data, nchans=64)`
  read as `this._params.nchans`, for values known from elsewhere. (construct
  `parse(data, **contextkw)`.)
- [ ] **`Default(wraps, value)`**: a field that can be left out when building.
  (construct `Default`.)
- [ ] **The element index in `Repeat`**, so an element can depend on its position.
  (construct `_index`.)
- [ ] **Enums that keep unknown values**, such as `Enum(..., strict=False)`
  returning the plain int, for formats that add values over time. (construct-typing
  `EnumBase`, structures and bread enum defaults.)
- [ ] **Check `Rebuild` values when parsing**, such as `Rebuild(..., check=True)`,
  so a stored length or count that doesn't match raises. (binmap
  `calculatedfield`.)
- [ ] **Repeats with a minimum and maximum count.** (structures `Repeat(start, stop)`.)
- [ ] **Fields left out of the result**, such as padding and reserved bytes, which
  now show up in every `Container`. (construct unnamed fields, binmap.)
- [ ] **A 100-nanosecond unit for `Timestamp`**, as used by Windows `FILETIME` and
  .NET ticks. (Found writing the SER cookbook recipe.)

## API and typing

- [ ] **`Struct.parse()` should return the subclass**, not `Struct`, so type
  checkers know the fields of `PNGHeader.parse(...)`. (construct-typing.)
- [ ] **An option to reject bytes left over after parsing**, such as
  `parse(data, strict=True)`, or a note in the tutorial pointing to `Terminated`.
  (pystructs `trailing_data`.)

## Debugging

- [ ] **Record each field's offset and size in the parsed result**, for hex viewers
  and debugging. (Kaitai `_debug`, bread `__offsets__`.)
- [ ] **A hex dump of parsed data with each field highlighted.** (dissect.cstruct
  `dumpstruct`.)
- [ ] **Drop into the debugger when a field fails.** (construct `Debugger`,
  structures `Debug`.)

## Maybe

- [ ] **Bit fields anywhere**, not only inside a `BitStruct` that adds up to
  whole bytes. This needs the stream to keep track of a bit position. (Kaitai `b3`,
  bitstruct, bread, duckparse `Bits[n]`.)
- [ ] **C alignment**: pad every field to its natural alignment, as a C compiler
  does, for reading memory dumps. (dissect.cstruct `align=True`.)
- [ ] **`BitStruct`s that parse into dataclasses.** (construct-typing
  `DataclassBitStruct`.)
- [ ] **A count-prefixed array**, as shorthand for `Rebuild` + `Repeat`. (construct
  `PrefixedArray`.)
- [ ] **Return one field of a sequence**, such as "skip the header, return the
  payload". (construct `FocusedSeq`.)
