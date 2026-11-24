# TODO

Features and fixes found by comparing pabo with other binary parsing libraries
(construct, structures, pystructs, duckparse, dissect.cstruct, Kaitai Struct,
binmap, dataclasses-struct, bitstruct, bread) and by writing the cookbook. Each
item says where the idea comes from. Within each section, the most useful come
first.

## Maybe

- [ ] **Bit fields anywhere**, not only inside a `BitStruct` that adds up to
  whole bytes. This needs the stream to keep track of a bit position. (Kaitai `b3`,
  bitstruct, bread, duckparse `Bits[n]`.)
