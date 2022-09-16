<div style="font-family:JetBrainsMono Nerd Font">
<img
    width=40%
    align="left"
    style="margin:0px 50px 25px 0px"
    alt="pabo: Binary parsing for dummies!"
    src="https://raw.githubusercontent.com/astrogewgaw/logos/main/rasters/pabo.png"
/>
<div align="right">

[![Doc Coverage][doc_cov]][interrogate]

![License][license]
![Stars][stars-badge]

[![Gitmoji][gitmoji-badge]][gitmoji]
[![Code style: black][black-badge]][black]

</div>

<div align="justify">

## What is this?

[**`pabo`**][pabo] makes parsing binary data so easy, anyone could do it! For
example, here is how you could use `pabo` to parse the beginning of a PNG file
and get the width and height of the image:

```python
import pabo as pb

png = pb.Spec(
    {
        "magic": pb.Const(
            b"\x89PNG\x0d\x0a\x1a\x0a",
            pb.Bytes(8),
        ),
        "ihdr_size": pb.Int(4, endian="big"),
        "ihdr_id": pb.Const(b"IHDR", pb.Bytes(4)),
        "width": pb.Int(4, endian="big"),
        "height": pb.Int(4, endian="big"),
    }
)

data = png.parse("example.png")
```

This would give you something like:

```python
{
     'magic': b'\x89PNG\r\n\x1a\n',
     'ihdr_size': 13,
     'ihdr_id': b'IHDR',
     'width': 602,
     'height': 172,
}
```

</div>

[numpy]: https://numpy.org
[doc_cov]: assets/doc_cov.svg
[attrs]: https://www.attrs.org
[gitmoji]: https://gitmoji.dev
[black]: https://github.com/psf/black
[pabo]: https://github.com/astrogewgaw/pabo
[priwo]: https://github.com/astrogewgaw/priwo
[construct]: https://github.com/construct/construct
[issues]: https://github.com/astrogewgaw/pabo/issues
[interrogate]: https://github.com/econchick/interrogate
[license]: https://img.shields.io/github/license/astrogewgaw/pabo?style=for-the-badge
[stars-badge]: https://img.shields.io/github/stars/astrogewgaw/pabo?style=for-the-badge
[black-badge]: https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge
[gitmoji-badge]: https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67.svg?style=for-the-badge
