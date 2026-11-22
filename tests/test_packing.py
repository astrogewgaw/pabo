import numpy as np
import pytest

from pabo.errors import PaboError
from pabo.packing import pack_bits, unpack_bits
from hypothesis import given
from hypothesis import strategies as st


@pytest.mark.parametrize("nbits", [1, 2, 3, 4, 5, 7, 8, 12, 16, 33, 64])
@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_roundtrip(nbits, bitorder):
    rng = np.random.default_rng(nbits)
    count = 8 * 3
    high = 2**nbits if nbits < 64 else 2**63
    values = rng.integers(0, high, size=count, dtype=np.uint64)
    raw = pack_bits(values, nbits, bitorder)
    assert len(raw) == count * nbits // 8
    np.testing.assert_array_equal(unpack_bits(raw, nbits, bitorder)[:count], values)


@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_one_bit_matches_numpy(bitorder):
    bits = np.random.default_rng(0).integers(0, 2, 64, dtype=np.uint8)
    raw = pack_bits(bits, 1, bitorder)
    assert raw == np.packbits(bits, bitorder=bitorder).tobytes()
    np.testing.assert_array_equal(unpack_bits(raw, 1, bitorder), bits)


def test_generic_matches_fast_path_layout():
    values = np.array([1, 2, 3, 0, 3, 2, 1, 0], dtype=np.uint8)
    for bitorder in ("big", "little"):
        bits = np.unpackbits(np.frombuffer(pack_bits(values, 2, bitorder), np.uint8), bitorder=bitorder)
        weights = [2, 1] if bitorder == "big" else [1, 2]
        np.testing.assert_array_equal(bits.reshape(-1, 2) @ weights, values)


def test_errors():
    with pytest.raises(PaboError):
        pack_bits([4], 2)
    with pytest.raises(PaboError):
        pack_bits([-1], 3)
    with pytest.raises(PaboError):
        unpack_bits(b"\x00", 0)
    with pytest.raises(PaboError):
        unpack_bits(b"\x00", 3, "middle")



@given(nbits=st.integers(1, 64), bitorder=st.sampled_from(["big", "little"]), data=st.data())
def test_roundtrip_property(nbits, bitorder, data):
    values = data.draw(st.lists(st.integers(0, 2**nbits - 1), max_size=40))
    raw = pack_bits(np.array(values, dtype=np.uint64), nbits, bitorder)
    assert len(raw) == -(-len(values) * nbits // 8)
    np.testing.assert_array_equal(unpack_bits(raw, nbits, bitorder)[: len(values)], values)
