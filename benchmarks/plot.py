"""
Plot pabo's benchmark results, for the documentation.

Usage:

    pytest benchmarks/bench_parse.py --benchmark-json=raw.json
    python benchmarks/plot.py raw.json

The first argument (optional) is pytest-benchmark's raw JSON output. It is
summarized into `benchmarks/results.json` (medians, interquartile ranges and
library versions; no hostname or other machine details). The summary is then
plotted with ultraplot into a light and a dark SVG under
`docs/source/_static/benchmarks/`, which the docs switch between with the
reader's theme. Without an argument, only the plots are redrawn from the
existing summary.
"""

import json
import platform
import subprocess
import sys
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import ultraplot as uplt

ROOT = Path(__file__).resolve().parent.parent
SUMMARY = ROOT / "benchmarks" / "results.json"
OUTPUT = ROOT / "docs" / "source" / "_static" / "benchmarks"

# What each benchmark group measures, in plot order.
GROUPS = {
    "header": "A PNG header: 5 fields, 24 bytes",
    "records": "1,000 records of (u16, u32, f32)",
    "array": "1,000,000 float32 values",
}

# How each implementation is named on the plot.
LABELS = {
    "pabo": "pabo",
    "pabo_array": "pabo, numpy records",
    "struct": "struct (stdlib)",
    "construct": "construct",
    "construct_compiled": "construct, compiled",
    "dissect": "dissect.cstruct",
    "kaitai": "Kaitai Struct",
    "bitstruct": "bitstruct",
    "structures": "structures",
    "bread": "bread",
    "binmap": "binmap",
    "duckparse": "duckparse",
    "pystructs": "pystructs",
    "dataclasses_struct": "dataclasses-struct",
}

# The packages whose versions are recorded with the results.
PACKAGES = (
    "construct",
    "dissect.cstruct",
    "kaitaistruct",
    "bitstruct",
    "structures",
    "bread",
    "binmap",
    "duckparse",
    "pystructs",
    "dataclasses-struct",
    "numpy",
)

# Colors (validated with the dataviz skill's palette checker): pabo is the point
# of the chart, so it gets the one hue; the alternatives are context, in gray.
THEMES = {
    "light": {
        "pabo": "#2a78d6",
        "other": "#898781",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "surface": "#fcfcfb",
    },
    "dark": {
        "pabo": "#3987e5",
        "other": "#898781",
        "ink": "#f0efec",
        "muted": "#c3c2b7",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "surface": "#1a1a19",
    },
}


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not installed"


def _commit() -> str:
    """
    The short hash of the commit being benchmarked (with "+dirty" for local edits).
    """

    try:
        run = lambda *args: subprocess.run(  # noqa: E731
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        return run("rev-parse", "--short", "HEAD") + (
            "+dirty" if run("status", "--porcelain", "src") else ""
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def summarize(raw: Path) -> dict:
    """
    Reduce pytest-benchmark's raw JSON to what the plots need.
    """

    data = json.loads(raw.read_text())
    results = []
    for bench in data["benchmarks"]:
        group = bench["group"]
        impl = bench["extra_info"]["implementation"]
        stats = bench["stats"]
        results.append(
            {
                "group": group,
                "implementation": impl,
                "median": stats["median"],
                "q1": stats["q1"],
                "q3": stats["q3"],
                "rounds": stats["rounds"],
            }
        )
    return {
        "date": date.today().isoformat(),
        "cpu": data["machine_info"].get("cpu", {}).get("brand_raw", "unknown"),
        "python": platform.python_version(),
        "commit": _commit(),
        "versions": {name: _version(name) for name in PACKAGES},
        "results": results,
    }


def _duration(seconds: float) -> str:
    """
    Format a duration with a sensible unit, such as `2.1 µs` or `310 ms`.
    """

    for unit, scale in (("s", 1), ("ms", 1e-3), ("µs", 1e-6), ("ns", 1e-9)):
        if seconds >= scale:
            value = seconds / scale
            return f"{value:.3g} {unit}" if value < 100 else f"{value:.0f} {unit}"
    return f"{seconds * 1e9:.2g} ns"


def plot(
    summary: dict,
    theme: str,
    folder: Path = OUTPUT,
    suffix: str = "svg",
    transparent: bool = True,
) -> Path:
    """
    Draw one panel per benchmark group, as a dot plot on a log time axis.

    The background is transparent, so the plot sits on the docs page's own
    background; pass `transparent=False` to fill it with the theme's surface
    (handy for previewing the dark theme).
    """

    colors = THEMES[theme]
    groups = [g for g in GROUPS if any(r["group"] == g for r in summary["results"])]
    counts = [sum(r["group"] == g for r in summary["results"]) for g in groups]
    uplt.rc.update(
        {
            "font.family": "sans-serif",
            "font.size": 9,
            # ultraplot colors labels through its own settings, as well as
            # matplotlib's, so both are set.
            "meta.color": colors["axis"],
            "axes.edgecolor": colors["axis"],
            "axes.labelcolor": colors["muted"],
            "label.color": colors["muted"],
            "tick.color": colors["axis"],
            "xtick.color": colors["axis"],
            "ytick.color": colors["axis"],
            "tick.labelcolor": colors["muted"],
            "xtick.labelcolor": colors["muted"],
            "ytick.labelcolor": colors["ink"],
            "grid.labelcolor": colors["muted"],
            "title.color": colors["ink"],
            "suptitle.color": colors["muted"],
            "text.color": colors["ink"],
            "grid.color": colors["grid"],
            "grid.linewidth": 0.8,
            "figure.facecolor": colors["surface"],
            "axes.facecolor": colors["surface"],
            "savefig.transparent": transparent,
            "savefig.facecolor": colors["surface"],
        }
    )
    # About a third of an inch per row, plus room for each panel's title and axis.
    fig, axs = uplt.subplots(
        nrows=len(groups),
        ncols=1,
        figwidth=6.4,
        figheight=0.32 * sum(counts) + 0.95 * len(groups) + 0.4,
        hratios=counts,
        share=False,
        hspace=5,
    )
    if not transparent:
        fig.patch.set_facecolor(colors["surface"])
    # Format the figure before the panels: formatting it afterwards resets their ticks.
    fig.format(
        suptitle="Time per parse: median, log scale, lower is better",
        suptitlecolor=colors["muted"],
        suptitleweight="normal",
    )
    for ax, group in zip(axs, groups):
        rows = sorted(
            (r for r in summary["results"] if r["group"] == group),
            key=lambda r: r["median"],
        )
        ys = list(range(len(rows)))[::-1]
        for y, row in zip(ys, rows):
            ours = row["implementation"].startswith("pabo")
            color = colors["pabo" if ours else "other"]
            ax.scatter(
                [row["median"]],
                [y],
                color=color,
                s=64,
                edgecolor="none",
                zorder=3,
            )
            ax.text(
                row["median"] * 1.6,
                y,
                _duration(row["median"]),
                va="center",
                ha="left",
                color=colors["ink"],
                fontweight="bold" if ours else "normal",
            )
        low = min(r["median"] for r in rows)
        high = max(r["median"] for r in rows)
        ax.format(
            xscale="log",
            xlim=(low / 3, high * 12),
            xformatter=lambda x, _: _duration(x),
            ylim=(-0.6, len(rows) - 0.4),
            yticks=ys,
            yticklabels=[
                LABELS.get(r["implementation"], r["implementation"]) for r in rows
            ],
            ytickminor=False,
            xtickminor=False,
            ygrid=False,
            xgrid=True,
            ltitle=GROUPS[group],
            titleweight="bold",
            titlecolor=colors["ink"],
        )
        for label in ax.get_yticklabels():
            label.set_color(colors["ink"])
            if label.get_text().startswith("pabo"):
                label.set_fontweight("bold")
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"parse-{theme}.{suffix}"
    fig.save(path)
    uplt.close(fig)
    return path


def main(argv: list[str]) -> None:
    """
    Summarize the raw results (if given), then draw the plots.
    """

    if len(argv) > 1:
        summary = summarize(Path(argv[1]))
        SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        print(f"Wrote {SUMMARY.relative_to(ROOT)}")
    summary = json.loads(SUMMARY.read_text())
    for theme in THEMES:
        print(f"Wrote {plot(summary, theme).relative_to(ROOT)}")


if __name__ == "__main__":
    main(sys.argv)
