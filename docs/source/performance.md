# Performance

How long pabo takes to parse three kinds of data, next to the standard library's
`struct` and other binary parsing libraries for Python (see [](comparison.md)).
Each dot is the median time for one parse, on a log scale.

```{image} _static/benchmarks/parse-light.svg
:class: only-light
:alt: Dot plots of parsing time per library for a PNG header, 1,000 records and 1,000,000 float32 values. For the header, struct and bitstruct are fastest, and pabo is among six libraries taking 1.6 to 2 microseconds. For the records, pabo's structured array is fastest at about 5 microseconds; as dicts, pabo is fourth, after struct and bitstruct, and about 2.8 times faster than the next library. For the array, pabo takes microseconds and every other library tens of milliseconds or more.
```

```{image} _static/benchmarks/parse-dark.svg
:class: only-dark
:alt: Dot plots of parsing time per library for a PNG header, 1,000 records and 1,000,000 float32 values. For the header, struct and bitstruct are fastest, and pabo is among six libraries taking 1.6 to 2 microseconds. For the records, pabo's structured array is fastest at about 5 microseconds; as dicts, pabo is fourth, after struct and bitstruct, and about 2.8 times faster than the next library. For the array, pabo takes microseconds and every other library tens of milliseconds or more.
```

## What is measured

Each library parses the data into whatever it usually returns: a dict, an object
or a dataclass per header and record, and a list (or for pabo, a numpy array) of
values. Where a library cannot check constants, the benchmark checks them by hand,
as the others do it themselves.

**A PNG header** (24 bytes: an 8-byte magic, a length, a chunk id, a width and a
height). `struct.unpack` is the floor: it returns a tuple and checks nothing.
bitstruct is a C extension that does the same at the bit level. The pure-Python
libraries come next, most of them within a few tenths of a microsecond of each
other; pabo compiles a specification of fixed-size fields into a single `struct`
call, and checks the constants against its result.

**1,000 records** of a `u16`, a `u32` and a `f32`, parsed into a list of dicts
(`Repeat` of a `Spec`). pabo parses repeats of fixed-size specifications in bulk,
with one `struct` call for all of them, so most of its time goes into making the
1,000 dicts. `struct.iter_unpack` makes tuples instead, and bitstruct unpacks
in C. With `Array(record)` instead, pabo returns the records as one numpy
structured array, a view of the bytes, which takes microseconds. binmap and
dataclasses-struct have no way to repeat a structure, so they are not in this
panel.

**1,000,000 float32 values.** pabo returns a numpy array that is a view of the
bytes being parsed, as `np.frombuffer` does, so the time does not grow with the
size of the array. Every other library builds a list or tuple of a million Python
floats. binmap has no arrays, so it is not in this panel.

The libraries, and the versions measured, are listed in `benchmarks/results.json`.
pystructs 0.4 needs Python 3.13, so it is left out of runs on older Pythons.

## Reproducing

The benchmarks are in `benchmarks/bench_parse.py`. With the `bench` extra
installed (`pip install -e ".[bench]"`), and duckparse from GitHub if you want it
(`pip install git+https://github.com/i64/duckparse`), run:

```bash
just bench-plot
```

This runs the benchmarks, summarizes them into `benchmarks/results.json` (which
records the date, commit, CPU and library versions), and redraws the plots on
this page. Libraries that are not installed are skipped. Timings depend on the
machine, so compare libraries within one run rather than across machines.
