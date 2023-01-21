#include <cstddef>
#include <cstdint>
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

namespace py = pybind11;

constexpr std::uint8_t LO2BITS{3};
constexpr std::uint8_t LO4BITS{15};
constexpr std::uint8_t HI2BITS{192};
constexpr std::uint8_t HI4BITS{240};
constexpr std::uint8_t LOMED2BITS{12};
constexpr std::uint8_t UPMED2BITS{48};

PYBIND11_MODULE(core, m) {
  m.def(
      "swap",
      [](py::array_t<std::uint8_t> x) {
        auto _x = x.unchecked<1>();
        auto _y = py::array_t<std::uint8_t>(_x.size());

        [](const std::uint8_t *x, std::uint8_t *y, std::size_t N) {
          for (std::size_t i = 0; i < N; i++)
            y[i] = std::uint8_t((x[i] * 0x0202020202ULL & 0x010884422010ULL) %
                                1023);
        }(_x.data(0), _y.mutable_data(0), _x.size());

        return _y;
      },
      py::arg("array"), "Swap bytes.");

  m.def(
      "pack",
      [](py::array_t<std::uint8_t> x, int n) {
        auto _x = x.unchecked<1>();
        auto _y = py::array_t<std::uint8_t>(_x.size() * n / 8);

        [](const std::uint8_t *x, std::uint8_t *y, std::size_t N, int n) {
          switch (n) {
          case 1:
            for (std::size_t i = 0; i < N * n / 8; i++)
              y[i] = std::uint8_t((x[i * 8 + 0] << 7) | (x[i * 8 + 1] << 6) |
                                  (x[i * 8 + 2] << 5) | (x[i * 8 + 3] << 4) |
                                  (x[i * 8 + 4] << 3) | (x[i * 8 + 5] << 2) |
                                  (x[i * 8 + 6] << 1) | (x[i * 8 + 7]));
            break;
          case 2:
            for (std::size_t i = 0; i < N * n / 8; i++)
              y[i] = std::uint8_t((x[i * 4] << 6) | (x[i * 4 + 1] << 4) |
                                  (x[i * 4 + 2] << 2) | x[i * 4 + 3]);
            break;
          case 4:
            for (std::size_t i = 0; i < N * n / 8; i++)
              y[i] = std::uint8_t((x[i * 2] << 4) | (x[i * 2 + 1]));
            break;
          }
        }(_x.data(0), _y.mutable_data(0), _x.size(), n);

        return _y;
      },
      py::arg("array"), py::arg("nbits"),
      "Pack 1, 2 and 4 bit data into an 8-bit numpy array.");

  m.def(
      "unpack",
      [](py::array_t<std::uint8_t> x, int n) {
        auto _x = x.unchecked<1>();
        auto _y = py::array_t<std::uint8_t>(_x.size() * 8 / n);

        [](const std::uint8_t *x, std::uint8_t *y, std::size_t N, int n) {
          switch (n) {
          case 1:
            for (std::size_t i = 0; i < N; i++)
              for (std::size_t j = 0; j < 8; j++)
                y[(i * 8) + (7 - j)] = (x[i] >> j) & 1;
            break;
          case 2:
            for (std::size_t i = 0; i < N; i++) {
              y[(i * 4) + 3] = (x[i] & LO2BITS);
              y[(i * 4) + 2] = (x[i] & LOMED2BITS) >> 2;
              y[(i * 4) + 1] = (x[i] & UPMED2BITS) >> 4;
              y[(i * 4) + 0] = (x[i] & HI2BITS) >> 6;
            }
            break;
          case 4:
            for (std::size_t i = 0; i < N; i++) {
              y[(i * 2) + 1] = (x[i] & LO4BITS);
              y[(i * 2) + 0] = (x[i] & HI4BITS) >> 4;
            }
            break;
          }
        }(_x.data(0), _y.mutable_data(0), _x.size(), n);

        return _y;
      },
      py::arg("array"), py::arg("nbits"),
      "Unpack 1, 2 and 4 bit data into an 8-bit numpy array.");
}
