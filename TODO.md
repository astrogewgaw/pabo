# TODO

Features and fixes found by comparing pabo with other binary parsing libraries
(construct, structures, pystructs, duckparse, dissect.cstruct, Kaitai Struct,
binmap, dataclasses-struct, bitstruct, bread) and by writing the cookbook. Each
item says where the idea comes from. Within each section, the most useful come
first.

## Constructs

## API and typing

- [ ] **Let type checkers accept `Struct` fields.** pyright rejects
  `width: int = pb.u32`, since a construct is not an `int`. `typing.dataclass_transform`
  (with constructs as field specifiers) may fix this, though probably not for the
  ready-made aliases such as `pb.u32`, which are instances rather than calls. (Found
  while making `Struct.parse()` return the subclass.)
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
