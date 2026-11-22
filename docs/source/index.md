# pabo

**Binary parsing for dummies!** Describe a binary layout once, then use the same
description to parse bytes into Python values and to build Python values back
into bytes.

```python
import pabo as pb

png = pb.Spec(
    {
        "magic": pb.Const(b"\x89PNG\r\n\x1a\n", pb.Bytes(8)),
        "ihdr_size": pb.u32,
        "ihdr_id": pb.Const(b"IHDR", pb.Bytes(4)),
        "width": pb.u32,
        "height": pb.u32,
    },
    endian="big",
)

header = png.parse("example.png")
header.width              # 602
png.build(header)         # back to the same bytes
```

```{toctree}
:maxdepth: 2
:caption: Contents

tutorial
cookbook
custom
comparison
api
changelog
```
