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
    rm -rf docs/build/*
    rm -rf .pytest_cache
    fd -I -e pyc -x rm -rf
    fd -I __pycache__ -x rm -rf

# Run tests.
@test: && clean
  pytest -vv tests

# Run tests with a coverage report.
@cov: && clean
  pytest --cov --cov-report=term tests

# Run benchmarks (needs pytest-benchmark; construct is optional).
@bench:
  pytest benchmarks/bench_parse.py --benchmark-group-by=group --benchmark-columns=mean,ops

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
