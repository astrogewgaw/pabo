#include <cstddef>
#include <cstdint>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include "pack.hpp"
#include "swap.hpp"
#include "unpack.hpp"

namespace py = pybind11;

py::array_t<std::uint8_t> swaps(py::array_t<std::uint8_t> X) {
  auto XX = X.unchecked<1>();
  const py::ssize_t size = XX.size();
  auto Y = py::array_t<std::uint8_t, py::array::c_style>({size});
  pabo::swaps(XX.data(0), Y.mutable_data(0), size);
  return Y;
}

py::array_t<std::uint8_t> pack(py::array_t<std::uint8_t> X, int nbits) {
  auto XX = X.unchecked<1>();
  const py::ssize_t size = XX.size();
  const py::ssize_t outsize = size * nbits / 8;
  auto Y = py::array_t<std::uint8_t, py::array::c_style>({outsize});
  pabo::pack(XX.data(0), Y.mutable_data(0), size, nbits);
  return Y;
}

py::array_t<std::uint8_t> unpack(py::array_t<std::uint8_t> X, int nbits) {
  auto XX = X.unchecked<1>();
  const py::ssize_t size = XX.size();
  const py::ssize_t outsize = size * 8 / nbits;
  auto Y = py::array_t<std::uint8_t, py::array::c_style>({outsize});
  pabo::unpack(XX.data(0), Y.mutable_data(0), size, nbits);
  return Y;
}

PYBIND11_MODULE(kernels, m) {
  m.doc() = "Kernels for pabo.";
  m.def("swaps", &swaps, py::arg("array"), "Swap bytes.");
  m.def("pack", &pack, py::arg("array"), py::arg("nbits"),
        "Pack 1, 2 and 4 bit data into an 8-bit numpy array.");
  m.def("unpack", &unpack, py::arg("array"), py::arg("nbits"),
        "Unpack 1, 2 and 4 bit data into an 8-bit numpy array.");
}
