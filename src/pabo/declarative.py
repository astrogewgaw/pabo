"""
Class-based specifications, parsed into typed dataclass instances.
"""

import dataclasses
import inspect
from collections.abc import Mapping
from typing import Any, ClassVar

from pabo.base import Construct
from pabo.context import Container
from pabo.hints import Endian, Source, Target
from pabo.specify import Specification
from pabo.wrappers import Const


class Struct:
    """
    Base class for specifications written as classes.

    Every class attribute that is a construct becomes a field, in the order
    they are written, and the class becomes a keyword-only dataclass:

        class PNGHeader(pb.Struct, endian="big"):
            magic: bytes = pb.Const(b"\\x89PNG\\r\\n\\x1a\\n", pb.Bytes(8))
            width: int = pb.Int(4)
            height: int = pb.Int(4)

        header = PNGHeader.parse("image.png")   # a PNGHeader instance
        header.width
        header.build()                          # back to bytes

    Constants default to their value, and other fields that can be built
    without a value (`Computed`, `Rebuild`, ...) default to None. Subclasses
    add fields after those of their parents. Use `OtherStruct.construct()` to
    nest one struct in another. The endianness given in the class statement
    applies to the numbers inside that don't set their own. Field names must
    not clash with the methods below (`parse`, `build`, `sizeof`, ...).
    """

    __pabo_fields__: ClassVar[dict[str, Construct]] = {}
    __pabo_spec__: ClassVar[Specification]
    __pabo_names__: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, endian: Endian | None = None, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        inherited = getattr(cls, "__pabo_spec__", None)
        fields = dict(cls.__pabo_fields__)
        own = {
            name: value
            for name, value in vars(cls).items()
            if isinstance(value, Construct)
        }
        fields.update(own)
        cls.__pabo_fields__ = fields
        if endian is None and inherited is not None:
            endian = inherited.endian
        cls.__pabo_spec__ = Specification(fields, endian=endian)

        try:
            hints = inspect.get_annotations(cls)
        except NameError:
            hints = {}
        annotations = {name: hints.get(name, Any) for name in own}
        for name, value in own.items():
            if isinstance(value, Const):
                setattr(cls, name, dataclasses.field(default=value.value))
            elif value._omittable():
                setattr(cls, name, dataclasses.field(default=None))
            else:
                delattr(cls, name)
        cls.__annotations__ = annotations
        dataclasses.dataclass(cls, kw_only=True)
        cls.__pabo_names__ = tuple(f.name for f in dataclasses.fields(cls))  # type: ignore[arg-type]

    @classmethod
    def fromdict(cls, data: Mapping[str, Any]) -> "Struct":
        """
        Create an instance from a dict of field values (such as a parsed `Container`).
        """

        return cls(**{name: data[name] for name in cls.__pabo_names__ if name in data})

    def todict(self) -> Container:
        """
        The field values, as a `Container`.
        """

        return Container({name: getattr(self, name) for name in self.__pabo_fields__})

    @classmethod
    def parse(cls, src: Source) -> "Struct":
        """
        Parse an instance from bytes, a path or a binary stream.
        """

        return cls.fromdict(cls.__pabo_spec__.parse(src))

    def build(self, src: Target = None, append: bool = False) -> bytes | None:
        """
        Build this instance into bytes (see `Construct.build`).
        """

        return self.__pabo_spec__.build(self.todict(), src, append)

    @classmethod
    def sizeof(cls, ctx: Mapping[str, Any] | None = None) -> int:
        """
        The size in bytes (see `Construct.sizeof`).
        """

        return cls.__pabo_spec__.sizeof(ctx)

    @classmethod
    def construct(cls) -> "StructConstruct":
        """
        A construct that parses into instances of this class, for nesting.
        """

        return StructConstruct(cls)


@dataclasses.dataclass
class StructConstruct(Construct):
    """
    A construct wrapping a `Struct` class: parses into, and builds from, its instances.

    Building also accepts a plain dict.
    """

    cls: type[Struct]

    def _size(self, ctx):
        return self.cls.__pabo_spec__._size(ctx)

    def _build(self, data, stream, ctx):
        values = data.todict() if isinstance(data, Struct) else data
        self.cls.__pabo_spec__._build(values, stream, ctx)
        return data

    def _parse(self, stream, ctx):
        return self.cls.fromdict(self.cls.__pabo_spec__._parse(stream, ctx))

    def _parsemany(self, stream, ctx, count: int) -> list | None:
        """
        Parse `count` instances in one go, as `Specification._parsemany` does.
        """

        unpacked = self.cls.__pabo_spec__._unpackmany(stream, ctx, count)
        if unpacked is None:
            return None
        # A plan covers every field, so its names are those of the dataclass.
        names, rows = unpacked
        cls = self.cls
        return [cls(**dict(zip(names, values))) for values in rows]
