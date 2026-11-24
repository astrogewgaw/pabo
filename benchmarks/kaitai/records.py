# This is a generated file! Please edit source .ksy file and use kaitai-struct-compiler to rebuild
# type: ignore

import kaitaistruct
from kaitaistruct import KaitaiStruct, KaitaiStream, BytesIO


if getattr(kaitaistruct, "API_VERSION", (0, 9)) < (0, 11):
    raise Exception(
        "Incompatible Kaitai Struct Python API: 0.11 or later is required, but you have %s"
        % (kaitaistruct.__version__)
    )


class Records(KaitaiStruct):
    def __init__(self, _io, _parent=None, _root=None):
        super(Records, self).__init__(_io)
        self._parent = _parent
        self._root = _root or self
        self._read()

    def _read(self):
        self.items = []
        for i in range(1000):
            self.items.append(Records.Record(self._io, self, self._root))

    def _fetch_instances(self):
        pass
        for i in range(len(self.items)):
            pass
            self.items[i]._fetch_instances()

    class Record(KaitaiStruct):
        def __init__(self, _io, _parent=None, _root=None):
            super(Records.Record, self).__init__(_io)
            self._parent = _parent
            self._root = _root
            self._read()

        def _read(self):
            self.a = self._io.read_u2le()
            self.b = self._io.read_u4le()
            self.c = self._io.read_f4le()

        def _fetch_instances(self):
            pass
