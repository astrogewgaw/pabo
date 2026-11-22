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

__all__ = [name for name in dir() if name[0] in "uif" and name[1:3].isdigit()]
