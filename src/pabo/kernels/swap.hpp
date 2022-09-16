#include <cstddef>
#include <cstdint>

namespace pabo {

void swaps(const std::uint8_t *X, std::uint8_t *Y, std::size_t size) {
  const int N = size;
  for (int i = 0; i < N; i++)
    Y[i] = (X[i] * 0x0202020202ULL & 0x010884422010ULL) % 1023;
}

} // namespace pabo
