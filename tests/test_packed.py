import numpy as np
import pytest

from pabo.packed import pack, unpack


@pytest.mark.parametrize("nbits", [1, 2, 4])
@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_pack_unpack_roundtrip(nbits, bitorder):
    rng = np.random.default_rng(42)
    values = rng.integers(0, 2**nbits, size=64, dtype=np.uint8)
    packed = pack(values, nbits=nbits, bitorder=bitorder)
    assert packed.size == values.size * nbits // 8
    np.testing.assert_array_equal(
        unpack(packed, nbits=nbits, bitorder=bitorder), values
    )


@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_1bit_matches_numpy(bitorder):
    data = np.array([0b10110010, 0b00001111], dtype=np.uint8)
    np.testing.assert_array_equal(
        unpack(data, nbits=1, bitorder=bitorder),
        np.unpackbits(data, bitorder=bitorder),
    )


def test_invalid_nbits():
    with pytest.raises(ValueError):
        unpack(np.zeros(1, dtype=np.uint8), nbits=3)


def test_pack_rejects_partial_bytes():
    with pytest.raises(ValueError):
        pack(np.zeros(7, dtype=np.uint8), nbits=1)


def test_pack_masks_out_of_range_values():
    assert pack(np.array([0xFF, 0x00], dtype=np.uint8), nbits=4).tolist() == [0xF0]


def test_accepts_read_only_input():
    data = np.frombuffer(b"\xa5", dtype=np.uint8)
    assert unpack(data, nbits=4).tolist() == [0xA, 0x5]


@pytest.mark.parametrize("nbits", [1, 2, 4])
def test_parallel_matches_serial(nbits):
    rng = np.random.default_rng(0)
    values = rng.integers(0, 2**nbits, size=8 * 100_000, dtype=np.uint8)
    np.testing.assert_array_equal(
        pack(values, nbits=nbits, parallel=True), pack(values, nbits=nbits)
    )
    packed = pack(values, nbits=nbits)
    np.testing.assert_array_equal(
        unpack(packed, nbits=nbits, parallel=True), unpack(packed, nbits=nbits)
    )


def _reference_pack(values, nbits, bitorder):
    bits = ((values[:, None] >> np.arange(nbits)[::-1]) & 1).astype(np.uint8)
    if bitorder == "little":
        bits = bits[:, ::-1]
    return np.packbits(bits.ravel(), bitorder=bitorder)


@pytest.mark.parametrize("nbits", [1, 2, 4])
@pytest.mark.parametrize("bitorder", ["big", "little"])
@pytest.mark.parametrize("parallel", [False, True])
def test_matches_numpy_reference(nbits, bitorder, parallel):
    rng = np.random.default_rng(nbits)
    values = rng.integers(0, 2**nbits, size=8 * 1000, dtype=np.uint8)
    expected = _reference_pack(values, nbits, bitorder)
    packed = pack(values, nbits=nbits, bitorder=bitorder, parallel=parallel)
    np.testing.assert_array_equal(packed, expected)
    np.testing.assert_array_equal(
        unpack(expected, nbits=nbits, bitorder=bitorder, parallel=parallel), values
    )
