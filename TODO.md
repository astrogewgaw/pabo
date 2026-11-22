# TODO

A roadmap for `pabo`, grouped by priority. The goal is the same as
[`construct`](https://github.com/construct/construct), which is declarative binary
parsing and building, but simpler and faster.

---

## 0. Blockers ✅ (fixed)

These come from the in-progress refactor (uncommitted changes on `main`).

- [x] **Fix the hook method names.** The refactor renamed `__size__`/`__parse__`/`__build__`
      to `__size`/`__parse`/`__build`. Python *name-mangles* these to
      `_Construct__size`, `_Bytes__size` and so on, so no subclass ever implements the
      abstract methods. Right now `pabo.Bytes(4)` raises
      `TypeError: Can't instantiate abstract class Bytes ...`. Cross-object calls such as
      `field.__build(...)` in `specify.py` are mangled too (`field._Specification__build`).
      - Pick one convention: single underscore (`_size`, `_parse`, `_build`) or the old
        dunders. Apply it everywhere. Some classes still use the dunder style
        (`PaddedString`, `Line`, `Adapted`, `Greedy.__parse__`).
      - The `Construct` docstring still says `__size__`/`__parse__`/`__build__`.
- [x] **`attrs` is imported but no longer a dependency.** `numeric.py` uses
      `from attrs import define`, but `pyproject.toml` only lists `numpy` and `beartype`.
      Either add it back or switch `numeric.py` to `@dataclass`, as the other modules
      already use. Mixing the two is also a problem: `@define` creates slotted classes, so
      `construct / "docs"` (which sets `self.docs`) raises `AttributeError` on `Int`,
      `Float` and `Array`.
- [x] **`Array` references the private `self.dtype.__format`.** This is mangled to
      `_Array__format` and doesn't exist. Expose a public `format`/`dtype` property on
      `Int`/`Float`.
- [x] **The C++ build is broken on Windows/MSVC.** `CMakeLists.txt` passes
      `-O3 -ffast-math` unconditionally. Guard these by compiler, and drop `-ffast-math`,
      which is pointless for integer bit-twiddling and unsafe in general.
- [x] **Add a test suite.** `tests/` now covers every public construct and the C++
      packer. Known bugs from §1 are `xfail(strict=True)`, so fixing one turns its test
      red until the marker is removed. Still to do: see §4.

## 1. Correctness bugs ✅ (fixed)

### Core (`base.py`)
- [x] `build()`/`parse()` use `isinstance(src, BinaryIO)`. `typing.BinaryIO` is not a
      runtime base class of real file objects (`BufferedWriter`, etc.), so building into
      an open file silently does nothing and returns `None`. Use duck typing
      (`hasattr(src, "write")`) or `io.IOBase`.
- [x] `build(data, "file.bin")` opens with `"ab"` (append), but `Const.build` opens with
      `"wb"`. Make these consistent. Truncate by default and add an explicit
      `append=True` option.
- [x] `parse()` accepts `bytes` but not `bytearray` or `memoryview`.
- [x] `PaboError` is decorated with `@dataclass`. Exceptions shouldn't be dataclasses, so
      remove the decorator.
- [x] `docs` is assigned dynamically instead of being a declared field. Declare it as a
      keyword-only field, as before the refactor.

### Numeric (`numeric.py`)
- [x] `Int`/`Float` with an unsupported width produce an empty format code and fail with
      a cryptic `struct.error`. Validate in `__post_init__`.
- [x] `endian` takes any string, and anything other than `"big"` silently means little.
      Use `Literal["little", "big", "native"]` and validate it.
- [x] `Array.size` returns the element count, not the byte size. `Specification.size`
      then gives wrong totals.
- [x] `Array.parse` with `packing` reads `count * width` bytes, but packed data occupies
      `count * packing / 8` bytes.
- [x] `Array` with `packing` passes arbitrary dtypes to `packed.pack`/`unpack`, which
      only accept `uint8`.
- [x] `Array.parse` with `count=-1` reads to EOF, and the length check
      `len(data) < self.count` never fires for `-1`. The byte length isn't checked to be a
      multiple of the element width either.

### Bits (`bits.py`)
- [x] `Bits.size` is in bits, but every other `size` is in bytes, so specs that mix them
      report the wrong size.
- [x] `Bits.parse` truncates the *packed* bytes to `count` before unpacking. It should
      unpack first, then truncate. Counts that aren't a multiple of 8 lose bits.
- [x] `Bits.build` assumes the input length is a multiple of 8, because `pack_1bit` drops
      the remainder.

### Bytes and strings (`bytes.py`, `strings.py`)
- [x] `Flag.parse` at EOF returns `True` (`b"" != b"\x00"`). Raise an error instead.
- [x] `Bytes.build` doesn't check `len(data) == count`, and `Bytes.parse` doesn't check
      for a short read.
- [x] `Line.parse` compares `data[-2:]`, which is a *list* of 1-byte objects, against
      `b"\r\n"`. The comparison is always unequal, so it loops until EOF and then raises.
- [x] `CString` only works for single-byte-null encodings. UTF-16 and UTF-32 need
      multi-byte terminators.
- [x] `PaddedString.build` doesn't check `len(raw) <= length`, so a negative pad silently
      produces wrong output.
- [x] `Padded.parse` strips *all* trailing `\x00`, which corrupts payloads that
      legitimately end in null bytes. `Padded.build` passes padded data to the wrapped
      construct instead of writing the padding separately.

### Wrappers (`wrappers.py`)
- [x] `Greedy.size` returns the bound method `self.wraps.__size` (not called).
- [x] `Greedy` only stops on `PaboError`. A short read in `Int`/`Float` raises
      `struct.error`, so `Greedy(Int(4))` crashes at EOF. It also doesn't rewind the
      stream after a partial element.
- [x] `Const.__build` has a different signature (`stream` only) from the base class.
      `Specification` calls `field.__build(data[name], stream)`, so users must supply
      values for constants and `Padding`. Constants should be filled in automatically
      when building.
- [x] `Sequential.build` uses `zip`, which silently truncates on a length mismatch. Use
      `zip(..., strict=True)`, and don't use a list comprehension for side effects.
- [x] `Sequential.size` filters out `None` sizes, which hides variable-size members.
- [x] `Prefixed.size` adds `pre.size + wraps.size`, which is meaningless for a
      variable-length payload.
- [x] `Adapted` field order is `wraps, post, pre`. `decode, encode` (or
      `parse, build`) with keyword names would be clearer.

### C++ extension (`packed.cpp`)
- [x] `size_t pos` is declared outside the OpenMP loop in `pack_*`, which causes a data
      race when `parallel=True`. Declare it inside the loop.
- [x] `USE_OPENMP` is never defined, and OpenMP is never linked in `CMakeLists.txt`, so
      `parallel` currently does nothing. Wire it up or remove it.
- [x] `pack()` doesn't check that `x.size()` is divisible by `8 / nbits`, so it silently
      drops trailing elements. It also doesn't mask inputs that exceed `nbits`.
- [x] `EmptyArr2D` is unused and uses `int totalsize`, which overflows for large arrays.
      Remove it.
- [x] `madvise(MADV_HUGEPAGE)` on `new[]` memory is fragile, and the offset math
      over-shoots when the pointer is already page-aligned. Use aligned allocation, or
      drop the optimisation unless a benchmark shows it helps.
- [x] Defaults disagree on bit order: C++ defaults to `"big"` and NumPy's `packbits`
      defaults to big, but `unpack_1bit<little>` is LSB-first. Document this and expose
      it as a `bitorder` option on `Bits`/`Array`.

## 2. Missing features (compared with `construct`)

### Context and dependent fields (the biggest gap)
- [x] **Reference earlier fields**, for example `Bytes(this.length)` or
      `Array(Int(4), count=this.n)`. Most real formats need this. Thread a context (a
      dict of already-parsed values plus a parent pointer for nested specs) through
      `_parse`/`_build`.
- [x] **Rebuild**: compute dependent fields automatically when building, for example a
      length prefix computed from `len(payload)`.
- [x] `Computed` for derived fields that occupy no bytes.

### Control flow
- [x] `If` / `IfThenElse` / `Optional`.
- [x] `Switch` (tagged unions keyed on a previously parsed field).
- [x] `RepeatUntil(predicate, ...)`, and a context-driven count for `Repeat`.
- [x] `StopIf` / `Terminated` (assert EOF).
- [x] `Check` / validation hooks, generalising `Const`.

### Types
- [ ] More integer types: 24-bit and other odd widths (`Int(3)`), 128-bit, variable-length
      integers (LEB128/VarInt, ZigZag), and `native` endianness.
- [ ] Half-precision floats (`Float(2)`, struct format `"e"`).
- [ ] `Enum` / `FlagsEnum` mapping integers to Python `enum.Enum`/`IntFlag`.
- [ ] `Timestamp` (Unix, MJD, and so on), which matters for astronomy formats.
- [ ] `GreedyBytes` / `GreedyString`.
- [ ] Configurable pad byte and pad direction for `Padded`/`PaddedString`.

### Bit-level structures
- [ ] `BitStruct` / bit fields: sub-byte integer fields inside a spec (for example a
      4-bit version and a 4-bit header length), with configurable bit order.
- [ ] Arbitrary `nbits` (3, 5, 12, ...) in the packer, not just 1, 2 and 4.

### Stream positioning
- [ ] `Seek`, `Tell`, `Pointer` (parse at an absolute offset), `Peek` (look ahead without
      consuming).
- [ ] `Aligned(n, ...)` / `AlignedSpec` for word-aligned layouts.
- [ ] `Lazy` fields and lazy arrays (offset recorded, data read on access).
- [ ] Zero-copy `mmap`/`np.memmap` parsing for large arrays. This is important for the
      `priwo` use case of multi-GB pulsar data files.

### Transforms
- [ ] `Compressed` (zlib, gzip, bz2, lzma), `Checksum` (CRC32, MD5, ...), and
      `Transformed` / `Restreamed` for encoded sub-streams.

### Ergonomics
- [ ] **A class-based declarative syntax**, which would set pabo apart from construct:
      ```python
      class PNGHeader(pb.Struct):
          magic: bytes = pb.Const(b"\x89PNG\r\n\x1a\n")
          width: int = pb.Int(4, endian="big")
      ```
      Parse into a typed dataclass instance instead of a plain `dict`.
- [ ] Attribute access on results (`data.width`), or return dataclasses.
- [ ] A spec-level default endianness so you don't repeat `endian="big"` on every field.
- [ ] Short aliases: `pb.u8`, `pb.u16be`, `pb.i32le`, `pb.f64`, and so on.
- [ ] Nested `Specification`s should round-trip, and an "embedded"/flattened variant
      should be available.
- [ ] Make `docs` (the `/` operator) actually useful: show docs in `repr`, error messages,
      and generated documentation.

### Debugging and diagnostics
- [x] Errors that include the **field path** (`png.ihdr.width`), the **stream offset**,
      and expected versus actual values.
- [ ] `Probe` / a debug mode that hex-dumps each field as it is parsed.
- [x] Consistent error message style (some are SHOUTING, some aren't).
- [x] A specific exception hierarchy (`StreamError`, `ConstError`, `SizeError`,
      `ValidationError`) under `PaboError`.

### Introspection
- [x] Separate the static size (known at definition) from the dynamic size (known after
      parsing). Return `None` or raise a clear `SizeofError` for variable-size
      constructs.
- [ ] `spec.describe()` / pretty `repr` showing the layout table (offsets, sizes, types).

## 3. Performance

- [ ] Compile fixed-size specs into a single `struct.Struct` format (or a NumPy
      structured `dtype`) and parse in one call instead of field by field.
- [ ] Read fixed-size arrays with `np.frombuffer` / `readinto` without intermediate
      copies.
- [ ] Consider making `beartype_this_package()` optional (env var or debug flag). Runtime
      type checking on every `_parse` call costs time in tight loops.
- [ ] Add benchmarks against `construct`, `struct` and NumPy structured dtypes
      (`pytest-benchmark` or `asv`).

## 4. Testing

- [ ] Unit tests per construct: parse, build and **round-trip**
      (`parse(build(x)) == x`).
- [ ] Property-based tests with `hypothesis` for numerics, strings and bit packing.
- [ ] Tests for the C++ packer against `np.packbits`/`np.unpackbits` (both bit orders,
      parallel and serial).
- [ ] Error-path tests: short reads, bad constants, wrong lengths.
- [ ] Real-world fixtures: PNG header, WAV/RIFF, ELF header, a SIGPROC filterbank header.
- [ ] Coverage reporting.

## 5. Packaging and CI

- [ ] **Add a CI workflow** that runs tests and lint on push and PR, across a
      Python × OS matrix. Currently only a release workflow exists.
- [ ] Modernise `release.yml`:
      - `actions/upload-artifact@v3` and `download-artifact@v3` have been shut down, so
        move to `@v4`. With v4, artifact names must be unique per matrix job, so download
        with `pattern:` and `merge-multiple: true`.
      - `pypa/cibuildwheel@v2.11.2` is very old and doesn't know about scikit-build-core
        or recent Python versions, so bump it.
      - `actions/checkout@v3` → `@v4`, and `gh-action-pypi-publish@v1.5.1` → `release/v1`
        with **trusted publishing** instead of `PYPI_PASSWORD`.
      - Add `fetch-depth: 0` to the checkout so `setuptools-scm` sees tags.
- [ ] Configure `[tool.cibuildwheel]` (skip PyPy/musl if unsupported, run tests in the
      wheels).
- [ ] Add `[project.optional-dependencies]` groups for `docs` and `dev` (`test` exists).
- [ ] Ship `py.typed` and type the public API properly (`parse` return types, generics on
      `Construct[T]`).
- [ ] Expose `pabo.__version__`.
- [ ] Add `ruff` (lint and format) and `mypy`/`pyright` config, plus `pre-commit`.
- [ ] Add a `.pyi` stub for the `packed` extension.

## 6. Documentation

- [ ] `.readthedocs.yaml` uses `ubuntu-20.04` and Python 3.9, but the package requires
      Python 3.10 or later. Update to `ubuntu-24.04` / Python 3.12 or later, and install
      the package so autodoc works.
- [ ] `conf.py` sets `html_static_path = ["static"]` and `templates_path = ["templates"]`,
      but neither directory exists. Update the copyright year.
- [ ] `docs/requirements.txt` lists `sphinx_rtd_theme`, which is unused (the docs use
      `furo`).
- [ ] Write real docs: a tutorial, an API reference (autodoc), a cookbook of real formats,
      a "pabo vs construct" comparison, and a guide to writing custom constructs.
- [ ] README:
      - The doc-coverage badge points to `assets/doc_cov.svg`, which this refactor
        deletes. Point it at `assets/interrogate.svg`.
      - Remove the dangling `[attrs]` / `[numpy]` link refs if unused.
      - Show `build()` as well as `parse()`.
      - The "Code style: black" badge should match whatever formatter is actually used.
- [ ] Docstrings: most constructs have one-line docstrings with no parameter docs. Fix the
      typo "functinality" in `base.py`.
- [ ] Add a `CHANGELOG.md`.
