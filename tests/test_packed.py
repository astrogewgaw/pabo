import numpy as np
import pytest

from pabo.packed import pack, unpack


@pytest.mark.parametrize("nbits", [1, 2, 4])
@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_pack_unpack_roundtrip(nbits, bitorder):
    """
    The C++ `pack` and `unpack` round-trip random 1, 2 and 4-bit values in both bit
    orders, with `pack` producing `count * nbits / 8` bytes.
    """

    rng = np.random.default_rng(42)
    values = rng.integers(0, 2**nbits, size=64, dtype=np.uint8)
    packed = pack(values, nbits=nbits, bitorder=bitorder)
    assert packed.size == values.size * nbits // 8
    np.testing.assert_array_equal(
        unpack(packed, nbits=nbits, bitorder=bitorder), values
    )


@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_1bit_matches_numpy(bitorder):
    """
    1-bit `unpack` gives the same result as `np.unpackbits` for both bit orders.
    """

    data = np.array([0b10110010, 0b00001111], dtype=np.uint8)
    np.testing.assert_array_equal(
        unpack(data, nbits=1, bitorder=bitorder),
        np.unpackbits(data, bitorder=bitorder),
    )


def test_invalid_nbits():
    """
    `unpack` raises `ValueError` for an unsupported `nbits` (3).
    """

    with pytest.raises(ValueError):
        unpack(np.zeros(1, dtype=np.uint8), nbits=3)


def test_pack_rejects_partial_bytes():
    """
    `pack` raises `ValueError` when the values do not fill a whole number of bytes.
    """

    with pytest.raises(ValueError):
        pack(np.zeros(7, dtype=np.uint8), nbits=1)


def test_pack_masks_out_of_range_values():
    """
    `pack` keeps only the low `nbits` bits of each value instead of letting high bits
    spill into its neighbours.
    """

    assert pack(np.array([0xFF, 0x00], dtype=np.uint8), nbits=4).tolist() == [0xF0]


def test_accepts_read_only_input():
    """
    `unpack` accepts a read-only array, such as one made with `np.frombuffer` on bytes.
    """

    data = np.frombuffer(b"\xa5", dtype=np.uint8)
    assert unpack(data, nbits=4).tolist() == [0xA, 0x5]


@pytest.mark.parametrize("nbits", [1, 2, 4])
def test_parallel_matches_serial(nbits):
    """
    With `parallel=True` (OpenMP), `pack` and `unpack` give the same output as the
    serial versions for 1, 2 and 4 bits on a large array.
    """

    rng = np.random.default_rng(0)
    values = rng.integers(0, 2**nbits, size=8 * 100_000, dtype=np.uint8)
    np.testing.assert_array_equal(
        pack(values, nbits=nbits, parallel=True), pack(values, nbits=nbits)
    )
    packed = pack(values, nbits=nbits)
    np.testing.assert_array_equal(
        unpack(packed, nbits=nbits, parallel=True), unpack(packed, nbits=nbits)
    )


def _referencepack(values, nbits, bitorder):
    """
    Pack `values` into `nbits` bits each with plain numpy, as a reference for the
    C++ packer (each value's bits go MSB first for big bit order, LSB first for little).
    """

    bits = ((values[:, None] >> np.arange(nbits)[::-1]) & 1).astype(np.uint8)
    if bitorder == "little":
        bits = bits[:, ::-1]
    return np.packbits(bits.ravel(), bitorder=bitorder)


@pytest.mark.parametrize("nbits", [1, 2, 4])
@pytest.mark.parametrize("bitorder", ["big", "little"])
@pytest.mark.parametrize("parallel", [False, True])
def test_matches_numpy_reference(nbits, bitorder, parallel):
    """
    The C++ `pack` matches the numpy reference packer and `unpack` inverts it, for every
    `nbits` in (1, 2, 4), both bit orders, with and without `parallel`.
    """

    rng = np.random.default_rng(nbits)
    values = rng.integers(0, 2**nbits, size=8 * 1000, dtype=np.uint8)
    expected = _referencepack(values, nbits, bitorder)
    packed = pack(values, nbits=nbits, bitorder=bitorder, parallel=parallel)
    np.testing.assert_array_equal(packed, expected)
    np.testing.assert_array_equal(
        unpack(expected, nbits=nbits, bitorder=bitorder, parallel=parallel), values
    )
