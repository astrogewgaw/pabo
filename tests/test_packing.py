import numpy as np
import pytest
from beartype.roar import BeartypeCallHintParamViolation
from hypothesis import given
from hypothesis import strategies as st

from pabo.errors import PaboError
from pabo.packing import packbits, unpackbits


@pytest.mark.parametrize("nbits", [1, 2, 3, 4, 5, 7, 8, 12, 16, 33, 64])
@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_roundtrip(nbits, bitorder):
    """
    `packbits` and `unpackbits` round-trip random values for widths from 1 to 64 bits,
    including the fast-path ones, in both bit orders, using `count * nbits / 8` bytes.
    """

    rng = np.random.default_rng(nbits)
    count = 8 * 3
    high = 2**nbits if nbits < 64 else 2**63
    values = rng.integers(0, high, size=count, dtype=np.uint64)
    raw = packbits(values, nbits, bitorder)
    assert len(raw) == count * nbits // 8
    np.testing.assert_array_equal(unpackbits(raw, nbits, bitorder)[:count], values)


@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_one_bit_matches_numpy(bitorder):
    """
    1-bit packing in either bit order gives the same bytes as `np.packbits`, and
    `unpackbits` inverts it.
    """

    bits = np.random.default_rng(0).integers(0, 2, 64, dtype=np.uint8)
    raw = packbits(bits, 1, bitorder)
    assert raw == np.packbits(bits, bitorder=bitorder).tobytes()
    np.testing.assert_array_equal(unpackbits(raw, 1, bitorder), bits)


def test_fast_path_layout_matches_documented_bit_order():
    """
    2-bit packing puts each value's bits in the order the bit order implies (MSB first
    for big, LSB first for little), the same layout the generic path uses.
    """

    values = np.array([1, 2, 3, 0, 3, 2, 1, 0], dtype=np.uint8)
    for bitorder in ("big", "little"):
        bits = np.unpackbits(
            np.frombuffer(packbits(values, 2, bitorder), np.uint8), bitorder=bitorder
        )
        weights = [2, 1] if bitorder == "big" else [1, 2]
        np.testing.assert_array_equal(bits.reshape(-1, 2) @ weights, values)


def test_errors():
    """
    `packbits` raises `PaboError` for values too large or negative, and `unpackbits` for
    `nbits` of zero or an unknown bit order.
    """

    with pytest.raises(PaboError):
        packbits([4], 2)
    with pytest.raises(PaboError):
        packbits([-1], 3)
    with pytest.raises(PaboError):
        unpackbits(b"\x00", 0)
    with pytest.raises((PaboError, BeartypeCallHintParamViolation)):
        unpackbits(b"\x00", 3, "middle")


@given(
    nbits=st.integers(1, 64),
    bitorder=st.sampled_from(["big", "little"]),
    data=st.data(),
)
def test_roundtrip_property(nbits, bitorder, data):
    """
    For any width from 1 to 64 bits, either bit order and any values that fit,
    `packbits` uses the fewest whole bytes and `unpackbits` recovers the values.
    """

    values = data.draw(st.lists(st.integers(0, 2**nbits - 1), max_size=40))
    raw = packbits(np.array(values, dtype=np.uint64), nbits, bitorder)
    assert len(raw) == -(-len(values) * nbits // 8)
    np.testing.assert_array_equal(
        unpackbits(raw, nbits, bitorder)[: len(values)], values
    )
