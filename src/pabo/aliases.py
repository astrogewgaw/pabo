"""
Short names for common numbers, such as `u16be` or `f64`.

The names without an `le`/`be` suffix take the endianness of the enclosing
specification (little-endian if it sets none).
"""

from pabo.numeric import Float, Int

u8 = Int(1)
i8 = Int(1, signed=True)

u16 = Int(2)
u16le = Int(2, endian="little")
u16be = Int(2, endian="big")
i16 = Int(2, signed=True)
i16le = Int(2, signed=True, endian="little")
i16be = Int(2, signed=True, endian="big")

u24 = Int(3)
u24le = Int(3, endian="little")
u24be = Int(3, endian="big")
i24 = Int(3, signed=True)
i24le = Int(3, signed=True, endian="little")
i24be = Int(3, signed=True, endian="big")

u32 = Int(4)
u32le = Int(4, endian="little")
u32be = Int(4, endian="big")
i32 = Int(4, signed=True)
i32le = Int(4, signed=True, endian="little")
i32be = Int(4, signed=True, endian="big")

u64 = Int(8)
u64le = Int(8, endian="little")
u64be = Int(8, endian="big")
i64 = Int(8, signed=True)
i64le = Int(8, signed=True, endian="little")
i64be = Int(8, signed=True, endian="big")

u128 = Int(16)
u128le = Int(16, endian="little")
u128be = Int(16, endian="big")
i128 = Int(16, signed=True)
i128le = Int(16, signed=True, endian="little")
i128be = Int(16, signed=True, endian="big")

f16 = Float(2)
f16le = Float(2, endian="little")
f16be = Float(2, endian="big")
f32 = Float(4)
f32le = Float(4, endian="little")
f32be = Float(4, endian="big")
f64 = Float(8)
f64le = Float(8, endian="little")
f64be = Float(8, endian="big")

__all__ = [
    "__all__",
    "f16",
    "f16be",
    "f16le",
    "f32",
    "f32be",
    "f32le",
    "f64",
    "f64be",
    "f64le",
    "i8",
    "i16",
    "i16be",
    "i16le",
    "i24",
    "i24be",
    "i24le",
    "i32",
    "i32be",
    "i32le",
    "i64",
    "i64be",
    "i64le",
    "i128",
    "i128be",
    "i128le",
    "u8",
    "u16",
    "u16be",
    "u16le",
    "u24",
    "u24be",
    "u24le",
    "u32",
    "u32be",
    "u32le",
    "u64",
    "u64be",
    "u64le",
    "u128",
    "u128be",
    "u128le",
]
