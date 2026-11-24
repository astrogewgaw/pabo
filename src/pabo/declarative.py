"""
Class-based specifications, parsed into typed dataclass instances.
"""

import dataclasses
import inspect
import sys
from collections.abc import Mapping
from typing import Any, ClassVar, TypeVar

from pabo.base import Construct
from pabo.context import Container
from pabo.hints import Endian, Source, Target
from pabo.specify import Specification
from pabo.wrappers import Const, Default

S = TypeVar("S", bound="Struct")

if sys.version_info >= (3, 11):
    from typing import dataclass_transform
else:  # Python 3.10 has no dataclass_transform; it only informs type checkers.

    def dataclass_transform(**kwargs: Any):
        """
        Stand-in for `typing.dataclass_transform`, which Python 3.10 lacks.
        """

        return lambda cls: cls


def _plain(construct: Const | Default) -> bool:
    """
    Whether the value of a `Const` or `Default` can be a dataclass default.

    A `Default` whose value is a function, or mutable (which dataclasses reject
    as a default), defaults to None instead, and is filled in when building.
    """

    value = construct.value
    if isinstance(construct, Const):
        return True
    return not callable(value) and type(value).__hash__ is not None


# Tells type checkers that subclasses are (keyword-only) dataclasses, so they know
# the arguments of `PNGHeader(width=..., ...)`.
@dataclass_transform(kw_only_default=True)
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

    Constants and `Default`s default to their value, and other fields that can
    be built without a value (`Computed`, `Rebuild`, ...) default to None. Subclasses
    add fields after those of their parents. Use `OtherStruct.construct()` to
    nest one struct in another. The endianness given in the class statement
    applies to the numbers inside that don't set their own. Field names must
    not clash with the methods below (`parse`, `build`, `sizeof`, ...).

    Type checkers know the arguments of the constructor and the type returned
    by `parse`, but flag each field line (a construct is not an `int`): add
    `# type: ignore[assignment]` to those lines if that matters to you.
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
        # Fields starting with an underscore are left out of the result, so they
        # are not dataclass fields either (and must build without a value).
        hidden = {name for name in own if name.startswith("_")}
        fields.update(own)
        cls.__pabo_fields__ = fields
        if endian is None and inherited is not None:
            endian = inherited.endian
        cls.__pabo_spec__ = Specification(fields, endian=endian)

        try:
            hints = inspect.get_annotations(cls)
        except NameError:
            hints = {}
        annotations = {name: hints.get(name, Any) for name in own if name not in hidden}
        for name in hidden:
            delattr(cls, name)
        for name, value in own.items():
            if name in hidden:
                continue
            if isinstance(value, (Const, Default)) and _plain(value):
                setattr(cls, name, dataclasses.field(default=value.value))
            elif value._omittable():
                setattr(cls, name, dataclasses.field(default=None))
            else:
                delattr(cls, name)
        cls.__annotations__ = annotations
        dataclasses.dataclass(cls, kw_only=True)
        cls.__pabo_names__ = tuple(f.name for f in dataclasses.fields(cls))  # type: ignore[arg-type]

    @classmethod
    def fromdict(cls: type[S], data: Mapping[str, Any]) -> S:
        """
        Create an instance from a dict of field values (such as a parsed `Container`).
        """

        return cls(**{name: data[name] for name in cls.__pabo_names__ if name in data})

    def todict(self) -> Container:
        """
        The field values, as a `Container`.
        """

        return Container({name: getattr(self, name) for name in self.__pabo_names__})

    @classmethod
    def parse(cls: type[S], src: Source, **params: Any) -> S:
        """
        Parse an instance from bytes, a path or a binary stream (with
        parameters, as in `Construct.parse`).
        """

        return cls.fromdict(cls.__pabo_spec__.parse(src, **params))

    def build(
        self, src: Target = None, append: bool = False, **params: Any
    ) -> bytes | None:
        """
        Build this instance into bytes (see `Construct.build`).
        """

        return self.__pabo_spec__.build(self.todict(), src, append, **params)

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
        names, rows = unpacked
        cls = self.cls
        if len(names) == len(cls.__pabo_names__):
            return [cls(**dict(zip(names, values))) for values in rows]
        # Some fields are left out of the result (their names start with "_").
        keep = [ix for ix, name in enumerate(names) if not name.startswith("_")]
        kept = [names[ix] for ix in keep]
        return [cls(**dict(zip(kept, [values[ix] for ix in keep]))) for values in rows]
