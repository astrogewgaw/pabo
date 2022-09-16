#include <cstddef>
#include <cstdint>

namespace pabo {

void pack(const std::uint8_t *X, std::uint8_t *Y, std::size_t size, int nbits) {
  int ix;
  unsigned char value;
  const int N = size;
  const int factor = 8 / nbits;

  switch (nbits) {
  case 1:
    for (int i = 0; i < N / factor; i++) {
      ix = i * 8;
      value = (X[ix + 0] << 7) | (X[ix + 1] << 6) | (X[ix + 2] << 5) |
              (X[ix + 3] << 4) | (X[ix + 4] << 3) | (X[ix + 5] << 2) |
              (X[ix + 6] << 1) | X[ix + 7];
      Y[i] = value;
    }
    break;
  case 2:
    for (int i = 0; i < N / factor; i++) {
      ix = i * 4;
      value = (X[ix] << 6) | (X[ix + 1] << 4) | (X[ix + 2] << 2) | X[ix + 3];
      Y[i] = value;
    }
    break;
  case 4:
    for (int i = 0; i < N / factor; i++) {
      ix = i * 2;
      value = (X[ix] << 4) | X[ix + 1];
      Y[i] = value;
    }
    break;
  }
}

} // namespace pabo
