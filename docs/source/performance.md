# Performance

How long pabo takes to parse three kinds of data, next to the standard library's
`struct`, numpy, and [construct](https://github.com/construct/construct) (plain and
compiled). Each dot is the median time for one parse, on a log scale.

```{image} _static/benchmarks/parse-light.svg
:class: only-light
:alt: Dot plots of parsing time per implementation for a PNG header, 1,000 records and 1,000,000 float32 values. pabo is faster than plain construct in all three, and slightly slower than construct's compiled mode for the PNG header.
```

```{image} _static/benchmarks/parse-dark.svg
:class: only-dark
:alt: Dot plots of parsing time per implementation for a PNG header, 1,000 records and 1,000,000 float32 values. pabo is faster than plain construct in all three, and slightly slower than construct's compiled mode for the PNG header.
```

## What is measured

**A PNG header** (24 bytes: an 8-byte magic, a length, a chunk id, a width and a
height) parsed into a dict of fields. pabo compiles a specification of fixed-size
fields into a single `struct` call, which puts it close to construct's compiled
mode without a separate compile step. Hand-written `struct.unpack` is the floor:
it skips everything a parsing library adds, such as checking the constants and
naming the fields.

**1,000 records** of a `u16`, a `u32` and a `f32`, parsed into a list of dicts
(`Repeat` of a `Spec`). pabo parses repeats of fixed-size specifications in bulk.
numpy's structured `np.frombuffer` is much faster still, because it returns a view
of the bytes, not 1,000 Python objects; use pabo's `Array` when a numpy array is
what you need.

**1,000,000 float32 values** as a numpy array (`Array(Float(4))`). Here numpy's
`np.frombuffer` returns a zero-copy view of bytes already in memory, so it takes
nanoseconds whatever the size, while pabo reads the bytes from a stream into a new
array. When parsing a *file* by path, pabo memory-maps it and returns a zero-copy
view too, so the cost no longer grows with the size of the array. construct builds
a Python list of a million floats.

## Reproducing

The benchmarks are in `benchmarks/bench_parse.py`. With the `bench` extra
installed (`pip install -e ".[bench]"`), run:

```bash
just bench-plot
```

This runs the benchmarks, summarizes them into `benchmarks/results.json` (which
records the date, commit, CPU and library versions), and redraws the plots on
this page. Timings depend on the machine, so compare implementations within one
run rather than across machines.
