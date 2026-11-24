import numpy as np
import pytest
from beartype.roar import BeartypeCallHintParamViolation
from hypothesis import given
from hypothesis import strategies as st

from pabo.errors import PaboError
from pabo.packing import packbits, unpackbits


@pytest.mark.parametrize("nbits", [1, 2, 4])
@pytest.mark.parametrize("bitorder", ["big", "little"])
def test_roundtrip(nbits, bitorder):
    """
    `packbits` and `unpackbits` round-trip random values for 1, 2 and 4 bits, in both
    bit orders, using `count * nbits / 8` bytes.
    """

    rng = np.random.default_rng(nbits)
    count = 8 * 3
    values = rng.integers(0, 2**nbits, size=count, dtype=np.uint8)
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
    `packbits` raises `PaboError` for values too large or negative, and both reject
    any width other than 1, 2 or 4 bits, and an unknown bit order.
    """

    with pytest.raises(PaboError):
        packbits([4], 2)
    with pytest.raises(PaboError):
        packbits([-1], 2)
    for nbits in (0, 3, 8, 12):
        with pytest.raises((PaboError, BeartypeCallHintParamViolation)):
            unpackbits(b"\x00", nbits)
        with pytest.raises((PaboError, BeartypeCallHintParamViolation)):
            packbits([0], nbits)
    with pytest.raises((PaboError, BeartypeCallHintParamViolation)):
        unpackbits(b"\x00", 3, "middle")


@given(
    nbits=st.sampled_from([1, 2, 4]),
    bitorder=st.sampled_from(["big", "little"]),
    data=st.data(),
)
def test_roundtrip_property(nbits, bitorder, data):
    """
    For 1, 2 and 4 bits, either bit order and any values that fit,
    `packbits` uses the fewest whole bytes and `unpackbits` recovers the values.
    """

    values = data.draw(st.lists(st.integers(0, 2**nbits - 1), max_size=40))
    raw = packbits(np.array(values, dtype=np.uint8), nbits, bitorder)
    assert len(raw) == -(-len(values) * nbits // 8)
    np.testing.assert_array_equal(
        unpackbits(raw, nbits, bitorder)[: len(values)], values
    )
