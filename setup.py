from setuptools import setup
from pybind11.setup_helpers import build_ext
from pybind11.setup_helpers import Pybind11Extension

if __name__ == "__main__":
    setup(
        ext_modules=[
            Pybind11Extension(
                "pabo.core",
                sorted(["src/pabo/core.cpp"]),
                extra_compile_args=[
                    "-O3",
                    "-ffast-math",
                    "-march=native",
                ],
            ),
        ],
        cmdclass={"build_ext": build_ext},
    )
