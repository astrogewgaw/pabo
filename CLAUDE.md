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
  __init__.py   public API re-exports; beartype_this_package() unless PABO_BEARTYPE=0
  base.py       Construct ABC, readexact(), scope() (adds field paths to errors)
  errors.py     PaboError and subclasses (StreamError, SizeofError, ValidationError, ...)
  context.py    Container, Context, `this` references, evaluate()
  hints.py      shared type hints: Source/Target, Readable/Writable protocols, Endian,
                BitOrder, Side, Whence, Dynamic, Condition, Key, Predicate
  numeric.py    Int (any width), Float, VarInt, ZigZag, Array (numpy, optional 1/2/4-bit packing)
  bits.py       Bits (one 0/1 byte per bit), BitStruct with BitInt/BitFlag/BitPadding
  bytes.py      Bytes, GreedyBytes, Flag, Padding
  strings.py    CString, Line, PaddedString, PascalString, GreedyString
  wrappers.py   Const, Greedy, Sequential, Repeat, Adapted, Prefixed, Padded
  specify.py    Specification (named fields -> Container), Embedded, _Plan (compiled
                fixed-size specs: one struct call, bulk parsing in Repeat)
  declarative.py Struct (class-based specs -> dataclasses), StructConstruct
  aliases.py    u8, u16be, i32le, f64, ... (unsuffixed ones inherit endianness)
  transforms.py Transformed, Compressed, Checksummed
  debug.py      Probe
  control.py    Computed, Rebuild, If, Optional, Switch, RepeatUntil, StopIf, Check, ...
  adapters.py   Enum, FlagsEnum, Timestamp
  stream.py     Seek, Tell, Pointer, Peek, Aligned, Lazy/LazyValue
  packing.py    packbits/unpackbits for 1, 2 or 4 bits (C++); other widths are rejected
  packed.cpp    nanobind C++ extension `pabo.packed`: pack()/unpack() for 1/2/4-bit data
  packed.pyi    type stub for it (regenerate with `python -m nanobind.stubgen -m pabo.packed`)
tests/          one test_<module>.py per source module (incl. test_packed.py)
benchmarks/     pytest-benchmark comparisons with struct, numpy and construct
docs/source/    Sphinx (furo + MyST) docs: tutorial, cookbook, custom, comparison, api
CHANGELOG.md    user-facing changes (keep the "Unreleased" section up to date)
```

Aliases exported from `pabo`: `Spec = Specification` and `Seq = Sequential`. Code
usually does `import pabo as pb`.

## Core design

Every construct is a `@dataclass` subclassing `Construct` (`base.py`) and implements
exactly three hooks, each taking the current `Context` (`ctx`):

- `_size(self, ctx) -> int`: the size **in bytes**. Raise `SizeofError` if the size
  is variable (for example greedy or `count < 0`).
- `_parse(self, stream, ctx) -> Any`: read from a binary stream and return a value.
- `_build(self, data, stream, ctx) -> Any`: write `data` to a binary stream and
  **return the value actually written** (usually `data`; computed for `Const`,
  `Rebuild`, ...). Specifications store it in the context for later fields.

Constructs that can be built with no value given override `_omittable()` to return
True (wrappers delegate it to what they wrap).

`Specification` creates a child `Context` per level (`ctx._` is the parent) and
stores each field's value under its name, so later fields can use `this.name`
or any `lambda ctx: ...`. Parameters that may depend on other fields are typed
`Dynamic` and resolved with `evaluate(value, ctx)`. When building, the context
starts as a copy of the full input dict. Composite constructs wrap each child in
`with scope(name, stream):` so errors carry the field path and offset.

`parse(path)` memory-maps the file, so the stream may be an `mmap.mmap`; `Array`
uses that to return zero-copy views, and `Lazy` values stay readable after
`parse` returns. Don't assume the stream is a regular file object.

The public `parse()`, `build()` and `size` live on the base class and handle the
input/output types: `bytes`/`bytearray`/`memoryview`, a `str`/`Path`, or a file-like
object (duck-typed with `hasattr(..., "read"/"write")`). `build()` to a path
truncates by default (`append=True` to append). Composite constructs call children's
`_parse`/`_build` directly on the shared stream, not the public methods.

Conventions to keep:

- **Hook names use a single underscore** (`_size`, not `__size`). Double-underscore
  names get mangled and break subclassing, as happened in a past refactor.
- **`size` is always in bytes**, including for `Bits` and packed `Array`.
- Use `readexact(stream, n)` for fixed-size reads so short reads raise `PaboError`
  and don't get silently truncated.
- **Raise a `PaboError` subclass** (`errors.py`) for every user-facing failure. Wrap
  `struct.error` and similar errors instead of letting them leak out, because
  `Greedy` relies on `PaboError` to detect the end of the stream. Messages are
  full sentences **in uppercase**, but interpolated values (`{data!r}`, field
  names), class names (`VarInt`) and literal values the user types (`'big'`)
  keep their case. `PaboError` formats messages as
  `"바보! <MSG> (AT <path>, OFFSET <n>) ABORT."`.
- Validate constructor arguments in `__post_init__` (widths, endianness, bit order,
  packing).
- `docs` is a keyword-only dataclass field, set with `construct / "description"`.
- Use stdlib `dataclasses`, not `attrs`. Runtime dependencies are only `numpy` and
  `beartype`.
- `beartype_this_package()` runs at import, so type hints on public signatures are
  **enforced at runtime**. Annotate them as strictly as possible (`Literal`s, the
  aliases in `hints.py`, `Callable[[...], ...]`), and also validate in
  `__post_init__`, since beartype can be turned off.
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
just cov        # tests with a coverage report
just lint       # ruff check, ruff format --check, pyright src, interrogate src
just bench      # benchmarks (needs the `bench` extra)
just clean      # remove caches/build junk (uses `fd`)
just docs       # sphinx-reload docs (or `just docs-build` for a one-off build)
```

Extras: `test` (pytest, pytest-cov, hypothesis), `bench`, `docs`, and `dev` (all
of them plus ruff, pyright, pre-commit, interrogate). CI (`.github/workflows/ci.yml`)
runs lint and the test matrix; `release.yml` builds wheels with cibuildwheel and
publishes with trusted publishing.

The editable install uses `--no-build-isolation`, so the build dependencies must
already be in the environment: `pip install scikit-build-core nanobind setuptools-scm`.
Run a single test with `pytest tests/test_numeric.py::test_name -vv`.

The version comes from git tags via setuptools-scm (written to `src/pabo/_version.py`,
which is not committed). Docstring coverage is checked by `interrogate`
(`fail-under = 85`, semiprivate names ignored, badge at `assets/interrogate.svg`). Python >= 3.10, so
`X | Y` unions, `match` and `zip(strict=True)` are all fine.

## Testing

- One test file per source module: `tests/test_<module>.py`. Add tests to the
  matching file rather than creating new ones.
- Every test (and test helper or test-local class) has a docstring saying what
  behaviour it checks, in the repo's style (triple quotes on their own lines).
- For every construct, test parse, build and **round-trip**
  (`c.parse(c.build(x)) == x`), plus error paths (short reads, wrong lengths, bad
  constants) asserting `pb.PaboError`.
- Known-but-unfixed bugs may be marked `pytest.mark.xfail(strict=True)`, so a fix
  turns the test red until the marker is removed.
- Test the C++ packer against `np.packbits`/`np.unpackbits` for both bit orders.
- Property-based tests use hypothesis; real-world formats (WAV, ELF, SIGPROC) live
  in `test_specify.py`.
- When asserting on bad constructor arguments, accept both `pb.PaboError` and
  `BeartypeCallHintParamViolation`, since beartype may reject a bad `Literal` first
  (and may be turned off).

## Style

- Code style: `ruff format` and `ruff check` (config in `pyproject.toml`), pyright in
  basic mode, and docstrings on everything public (interrogate enforces this).
- Avoid underscores inside function and method names (`readexact`, `packbits`,
  `todict`); a single leading underscore for private helpers is fine
  (`_parsefields`). Test functions keep pytest's `test_snake_case` names.
- Hot internal paths (`Context`, `Specification._parsefields`, ...) are marked
  `@typing.no_type_check` so beartype skips them; keep it that way for speed. Every
  such site has a comment saying why (the reasoning is in `context.py`'s docstring).
  Don't add it to unannotated functions: beartype already ignores those.
- Commits use [gitmoji](https://gitmoji.dev) prefixes in `:code:` form, for example
  `:bug: Fix bug when reading in arrays.` or `:recycle: Refactoring.`.
- Record user-facing changes (features, fixes, breaking changes) in `CHANGELOG.md`.

## Gotchas

- Don't name a construct's dataclass field `size`: it would shadow the `size`
  property (use `length`, as `Transformed` does).
- `this.n == 0` is a plain bool (references compare by path), not an expression.
- `Specification._plan` must give exactly the same results as the field-by-field
  path; when unsure, return None from `_Plan.compile` and let the slow path run.
