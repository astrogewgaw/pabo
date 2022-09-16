#include <cstddef>
#include <cstdint>

constexpr std::uint8_t LO2BITS{3};
constexpr std::uint8_t LO4BITS{15};
constexpr std::uint8_t HI2BITS{192};
constexpr std::uint8_t HI4BITS{240};
constexpr std::uint8_t LOMED2BITS{12};
constexpr std::uint8_t UPMED2BITS{48};

namespace pabo {

void unpack(const std::uint8_t *X, std::uint8_t *Y, std::size_t size,
            int nbits) {
  const int N = size;

  switch (nbits) {
  case 1:
    for (size_t i = 0; i < N; i++) {
      for (size_t j = 0; j < 8; j++)
        Y[(i * 8) + (7 - j)] = (X[i] >> j) & 1;
    }
    break;
  case 2:
    for (int i = 0; i < N; i++) {
      Y[(i * 4) + 3] = X[i] & LO2BITS;
      Y[(i * 4) + 2] = (X[i] & LOMED2BITS) >> 2;
      Y[(i * 4) + 1] = (X[i] & UPMED2BITS) >> 4;
      Y[(i * 4) + 0] = (X[i] & HI2BITS) >> 6;
    }
    break;
  case 4:
    for (int i = 0; i < N; i++) {
      Y[(i * 2) + 1] = X[i] & LO4BITS;
      Y[(i * 2) + 0] = (X[i] & HI4BITS) >> 4;
    }
    break;
  }
}

} // namespace pabo
