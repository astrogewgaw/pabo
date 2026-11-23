# Writing your own constructs

Every construct is a dataclass that subclasses `pabo.Construct` and implements
three methods. Each takes `ctx`, the `Context` holding the fields parsed (or being
built) so far:

`_size(self, ctx) -> int`
: The size in bytes. Raise `pabo.SizeofError` if it depends on the data.

`_parse(self, stream, ctx)`
: Read from the binary stream and return the value.

`_build(self, data, stream, ctx)`
: Write `data` to the stream, and return the value that was written (usually
  `data` itself).

Here is a construct for a 32-bit fixed-point number with 16 fractional bits:

```python
from dataclasses import dataclass

import pabo as pb
from pabo.base import readexact


@dataclass
class Fixed16(pb.Construct):
    """
    A signed 16.16 fixed-point number.
    """

    endian: str = "big"

    def _size(self, ctx):
        return 4

    def _parse(self, stream, ctx):
        raw = readexact(stream, 4)
        return int.from_bytes(raw, self.endian, signed=True) / 65536

    def _build(self, data, stream, ctx):
        value = round(data * 65536)
        try:
            stream.write(value.to_bytes(4, self.endian, signed=True))
        except OverflowError as error:
            raise pb.ValidationError(f"{data} DOES NOT FIT IN 16.16 FIXED POINT.") from error
        return data


Fixed16().parse(b"\x00\x01\x80\x00")    # 1.5
```

A few conventions keep custom constructs working well with the rest of pabo:

- Use `readexact(stream, n)` for fixed-size reads, so short reads raise
  `StreamError` instead of silently giving less data.
- Raise a subclass of `pabo.PaboError` for every failure (`ValidationError`
  for bad values, `StreamError` for stream problems). `Greedy` and `Optional`
  rely on this to know when to stop.
- Validate arguments in `__post_init__`.
- If a parameter may depend on other fields, accept a value or a function and
  resolve it with `pabo.context.evaluate(value, ctx)`.
- If your construct wraps others, call their `_parse`/`_build`/`_size` methods
  with the same stream and context, and wrap each child in
  `with pabo.base.scope(name, stream):` so that errors carry the path to it.
- If your construct can be built without a value (it is constant, or computed),
  override `_omittable` to return True, so specifications don't ask for one.

Often you don't need a new construct at all: `Adapted(wraps, decode, encode)` turns
the value of an existing construct into something else and back.

```python
fixed16 = pb.Adapted(pb.i32be, decode=lambda x: x / 65536, encode=lambda x: round(x * 65536))
```
