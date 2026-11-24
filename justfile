pkg  := "pabo"

alias t := test
alias d := docs
alias c := clean
alias i := install
alias u := uninstall


# List available commands.
default:
  @just --choose


# Clean up.
@clean:
    echo "Cleaning..."
    rm -rf tmp
    rm -rf dist
    rm -rf .eggs
    rm -rf .coverage
    rm -rf .mypy_cache
    rm -rf docs/build docs/_build
    rm -rf .pytest_cache
    fd -I -e pyc -x rm -rf
    fd -I __pycache__ -x rm -rf

# Run tests.
@test: && clean
  pytest -vv tests

# Lint, check formatting, type-check and check docstring coverage.
@lint:
  ruff check .
  ruff format --check .
  pyright src
  interrogate src

# Run tests with a coverage report.
@cov: && clean
  pytest --cov --cov-report=term tests

# Run benchmarks (needs pytest-benchmark; construct is optional).
@bench:
  pytest benchmarks/bench_parse.py --benchmark-group-by=group --benchmark-columns=mean,ops

# Run benchmarks, then summarize them and redraw the plots in the docs.
@bench-plot:
  pytest benchmarks/bench_parse.py --benchmark-warmup=on --benchmark-min-time=0.05 --benchmark-json=benchmarks/raw.json
  python benchmarks/plot.py benchmarks/raw.json
  rm benchmarks/raw.json

# Install.
@install: && clean
    echo "Installing..."
    pip install --no-build-isolation -Ceditable.rebuild=true -ve .

# Uninstall.
@uninstall: && clean
    echo "Uninstalling {{pkg}}..."
    pip uninstall {{pkg}}
    rm -rf build
    rm -rf src/{{pkg}}.egg-info
    rm -rf src/{{pkg}}/_version.py

# Build docs.
@docs:
    echo "Building docs for {{pkg}}..."
    sphinx-reload docs

# Build the docs once into docs/build.
@docs-build:
    sphinx-build -b html docs/source docs/build
