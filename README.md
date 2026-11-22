<div align="center">
<img 
    alt="pabo: Binary parsing for dummies!"
    src="https://raw.githubusercontent.com/astrogewgaw/logos/main/rasters/pabo.png"
/>
</div>
<br/><br/>
<div align="center">

[![Doc Coverage][doc_cov]][interrogate]

![License][license]
![Stars][stars-badge]

[![Gitmoji][gitmoji-badge]][gitmoji]
[![Ruff][ruff-badge]][ruff]

</div>

<div align="justify">

<h2>What is this?</h2>

Parsing binary data from Python has always been a bit of a pain, thanks to the
weirdly designed [**`struct`**][struct] module in Python's standard library.
`struct` uses format strings to specify the layout of binary data, where each
character specifies the type of data being packed/unpacked. But no can remember
the format characters to begin with! This has led to numerous packages cropping
in an attempt to solve the problem, such as:

* [**`bread`**][bread]
* [**`construct`**][construct]
* [**`structures`**][structures]

and many others. [**`pabo`**][pabo] is my response to such packages. It makes
parsing binary data so easy, anyone could do it! For example, here is how you
would parse the beginning of a PNG file to get the width and height of the
image:

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

which would return a dictionary with the parsed data, like so:

```python
{
    "magic": b"\x89PNG\r\n\x1a\n",
    "ihdr_size": 13,
    "ihdr_id": b"IHDR",
    "width": 602,
    "height": 172,
}
```

For more real examples, check out the [**`priwo`**][priwo] package, which uses
`pabo` to parse pulsar data from binary files (in fact, many of `pabo`'s
features are directly motivated by their need in `priwo`!). The
[**documentation**][docs] has a tutorial, a cookbook of real formats, and a
comparison with `construct`.

<h2>Installation</h2>

Installing [**`pabo`**][pabo] is as easy as:

```bash
pip install pabo
```

<h2>Philosophy</h2>

The philosophy behind `pabo` is: be simple, yet be fast and full of features.
This implies that I deliberately avoid coding in features that are too magical
or obscure, in contrast to other packages, such as `construct`. This allows
users of `pabo` to also become contributors, since the internals of `pabo` are
clean and easy-to-understand.

</div>

[docs]: https://pabo.readthedocs.io
[ruff]: https://github.com/astral-sh/ruff
[gitmoji]: https://gitmoji.dev
[bread]: https://github.com/alexras/bread
[pabo]: https://github.com/astrogewgaw/pabo
[priwo]: https://github.com/astrogewgaw/priwo
[construct]: https://github.com/construct/construct
[issues]: https://github.com/astrogewgaw/pabo/issues
[structures]: https://github.com/malinoff/structures
[interrogate]: https://github.com/econchick/interrogate
[struct]: https://docs.python.org/3/library/struct.html
[doc_cov]: https://raw.githubusercontent.com/astrogewgaw/pabo/main/assets/interrogate.svg
[license]: https://img.shields.io/github/license/astrogewgaw/pabo?style=for-the-badge
[stars-badge]: https://img.shields.io/github/stars/astrogewgaw/pabo?style=for-the-badge
[ruff-badge]: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=for-the-badge
[gitmoji-badge]: https://img.shields.io/badge/gitmoji-%20😜%20😍-FFDD67.svg?style=for-the-badge
