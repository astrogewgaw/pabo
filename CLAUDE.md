# CLAUDE.md

## What pabo is

`pabo` ("Binary parsing for dummies!") is a declarative binary parsing and building
library for Python. It is the author's take on
[`construct`](https://github.com/construct/construct): you describe a binary layout
once, as a tree of `Construct` objects, then use the same description to **parse**
bytes into Python values and to **build** Python values back into bytes.

The main downstream user is [`priwo`](https://github.com/astrogewgaw/priwo), which
reads pulsar astronomy data files (SIGPROC filterbank and similar). Many features
exist because priwo needs them. Large numeric arrays and sub-byte (1/2/4-bit) packed
data are first-class concerns.

### Philosophy (from the README)

Be simple, but fast and full of features. **Deliberately avoid features that are too
magical or obscure**, which is where pabo differs from `construct`. The internals
should stay clean enough that users can become contributors. When adding a feature
that construct has, prefer the plainest design that covers real use cases over
matching construct's API one to one. Don't add metaclass tricks, implicit global
state, or operator overloading beyond what already exists.

## Layout

```
src/pabo/
  __init__.py   public API re-exports, plus beartype_this_package()
  base.py       Construct ABC, PaboError, read_exactly()
  numeric.py    Int, Float (struct-backed), Array (numpy-backed, optional bit packing)
  bits.py       Bits (bit-level fields, one 0/1 byte per bit)
  bytes.py      Bytes, Flag, Padding
  strings.py    CString, Line, PaddedString, PascalString
  wrappers.py   Const, Greedy, Sequential, Repeat, Adapted, Prefixed, Padded
  specify.py    Specification (ordered dict of named fields -> dict)
  packed.cpp    nanobind C++ extension `pabo.packed`: pack()/unpack() for 1/2/4-bit data
tests/          one test_<module>.py per source module (incl. test_packed.py)
docs/           Sphinx (furo) docs; still largely unwritten
TODO.md         roadmap: blockers, bugs, missing features vs construct, perf, CI, docs
```

Aliases exported from `pabo`: `Spec = Specification` and `Seq = Sequential`. Code
usually does `import pabo as pb`.

## Core design

Every construct is a `@dataclass` subclassing `Construct` (`base.py`) and implements
exactly three hooks:

- `_size(self) -> int`: the static size **in bytes**. Raise `PaboError` if the size
  is variable (for example greedy or `count < 0`).
- `_parse(self, stream) -> Any`: read from a binary stream and return a value.
- `_build(self, data, stream) -> None`: write `data` to a binary stream.

The public `parse()`, `build()` and `size` live on the base class and handle the
input/output types: `bytes`/`bytearray`/`memoryview`, a `str`/`Path`, or a file-like
object (duck-typed with `hasattr(..., "read"/"write")`). `build()` to a path
truncates by default (`append=True` to append). Composite constructs call children's
`_parse`/`_build` directly on the shared stream, not the public methods.

Conventions to keep:

- **Hook names use a single underscore** (`_size`, not `__size`). Double-underscore
  names get mangled and break subclassing, as happened in a past refactor.
- **`size` is always in bytes**, including for `Bits` and packed `Array`.
- Use `read_exactly(stream, n)` for fixed-size reads so short reads raise `PaboError`
  and don't get silently truncated.
- **Raise `PaboError`** for every user-facing failure. Wrap `struct.error` and
  similar errors instead of letting them leak out, because `Greedy` relies on
  `PaboError` to detect the end of the stream. `PaboError` formats messages as
  `"바보! <msg> ABORT."`.
- Validate constructor arguments in `__post_init__` (widths, endianness, bit order,
  packing).
- `docs` is a keyword-only dataclass field, set with `construct / "description"`.
- Use stdlib `dataclasses`, not `attrs`. Runtime dependencies are only `numpy` and
  `beartype`.
- `beartype_this_package()` runs at import, so type hints on public signatures are
  **enforced at runtime**. Annotate them accurately.
- `Const` values (and therefore `Padding`) may be left out when building a
  `Specification`. They are filled in automatically.
- Endianness is `Literal["little", "big", "native"]`, default `"little"`. Bit order
  is `"big"` (first element in the MSB) or `"little"`, default `"big"`, which
  matches `np.packbits`.

## C++ extension (`packed.cpp`)

Built with **scikit-build-core + nanobind + CMake** (`CMakeLists.txt`), as a
stable-ABI (`cp312`) module installed as `pabo.packed`. It provides
`pack(x, nbits, bitorder="big", parallel=False)` and `unpack(...)` on contiguous
`uint8` numpy arrays for `nbits` in {1, 2, 4}. OpenMP is linked when available and
enables `USE_OPENMP`. Loop indices are signed (`std::ptrdiff_t`) because MSVC only
supports OpenMP 2.0. Keep compiler flags portable (Linux/macOS/Windows wheels are
built with cibuildwheel).

Editing `packed.cpp` needs a rebuild. With the editable install below, it rebuilds
automatically on import.

## Commands

Uses [`just`](https://github.com/casey/just) (see `justfile`):

```bash
just install    # pip install --no-build-isolation -Ceditable.rebuild=true -ve .
just test       # pytest -vv tests   (then runs `just clean`)
just clean      # remove caches/build junk (uses `fd`)
just docs       # sphinx-reload docs
```

The editable install uses `--no-build-isolation`, so the build dependencies must
already be in the environment: `pip install scikit-build-core nanobind setuptools-scm`.
Run a single test with `pytest tests/test_numeric.py::test_name -vv`.

The version comes from git tags via setuptools-scm (written to `src/pabo/_version.py`,
which is not committed). Docstring coverage is checked by `interrogate`
(`fail-under = 85`, badge at `assets/interrogate.svg`). Python >= 3.10, so
`X | Y` unions, `match` and `zip(strict=True)` are all fine.

## Testing

- One test file per source module: `tests/test_<module>.py`. Add tests to the
  matching file rather than creating new ones.
- For every construct, test parse, build and **round-trip**
  (`c.parse(c.build(x)) == x`), plus error paths (short reads, wrong lengths, bad
  constants) asserting `pb.PaboError`.
- Known-but-unfixed bugs may be marked `pytest.mark.xfail(strict=True)`, so a fix
  turns the test red until the marker is removed.
- Test the C++ packer against `np.packbits`/`np.unpackbits` for both bit orders.

## Style

- Code style: black-compatible formatting, with module and class docstrings on
  everything public (interrogate enforces this).
- Commits use [gitmoji](https://gitmoji.dev) prefixes in `:code:` form, for example
  `:bug: Fix bug when reading in arrays.` or `:recycle: Refactoring.`.
- When you fix a bug or implement a feature listed in `TODO.md`, tick it off there.

## Roadmap context

See `TODO.md`. The biggest gap relative to construct is **context and dependent
fields**: referencing earlier fields (`Bytes(this.length)`), rebuilding computed
fields, `Computed`, `Switch`, `If`, `RepeatUntil`, and so on. Also planned: a
class-based declarative syntax, compiling fixed-size specs to a single `struct` or
numpy structured dtype for speed, and mmap/lazy parsing for multi-GB files. Design
new features with these in mind, for example by threading a context through
`_parse`/`_build` in the future, but don't build speculative infrastructure ahead of
the feature that needs it.
