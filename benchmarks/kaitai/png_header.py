# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import KaitaiStruct, KaitaiStream, BytesIO


if getattr(kaitaistruct, "API_VERSION", (0, 9)) < (0, 11):
    raise Exception(
        "Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s"
        % (kaitaistruct.__version__)
    )


class PngHeader(KaitaiStruct):
    def __init__(self, _io, _parent=None, _root=None):
        super(PngHeader, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self
        self._read()

    def _read(self):
        self.magic = self._io.read_bytes(8)
        if not self.magic == b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a":
            raise kaitaistruct.ValidationNotEqualError(
                b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a", self.magic, self._io, "/seq/0"
            )
        self.ihdr_size = self._io.read_u4be()
        self.ihdr_id = self._io.read_bytes(4)
        if not self.ihdr_id == b"\x49\x48\x44\x52":
            raise kaitaistruct.ValidationNotEqualError(
                b"\x49\x48\x44\x52", self.ihdr_id, self._io, "/seq/2"
            )
        self.width = self._io.read_u4be()
        self.height = self._io.read_u4be()

    def _fetch_instances(self):
        pass
