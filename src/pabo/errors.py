"""
Errors raised by pabo.
"""


class PaboError(Exception):
    """
    Base class for all errors in pabo.

    `path` lists the fields being parsed or built when the error happened, from
    the outermost inwards, and `offset` is the stream position where the
    innermost of those fields started (None if unknown). `docs` holds the docs
    of the innermost documented field on the path.
    """

    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg
        self.path: list[str] = []
        self.offset: int | None = None
        self.docs: str = ""

    @property
    def where(self) -> str:
        """
        The field path as a string, such as `header.sizes[2]`.
        """

        out = ""
        for name in self.path:
            out += name if (not out or name.startswith("[")) else "." + name
        return out

    def __str__(self) -> str:
        parts = []
        if self.path:
            parts.append(f"AT {self.where}")
        if self.docs:
            parts.append(repr(self.docs))
        if self.offset is not None:
            parts.append(f"OFFSET {self.offset}")
        where = f" ({', '.join(parts)})" if parts else ""
        return f"바보! {self.msg}{where} ABORT."

    def __reduce__(self):
        state = {"path": self.path, "offset": self.offset, "docs": self.docs}
        return (type(self), (self.msg,), state)


class StreamError(PaboError):
    """
    The stream ended early, had data left over, or could not be read/written.
    """


class SizeofError(PaboError):
    """
    A size was asked for, but it cannot be known without the data.
    """


class ValidationError(PaboError):
    """
    A value failed a check while parsing or building.
    """


class ConstError(ValidationError):
    """
    A constant did not have the expected value.
    """


class ContextError(PaboError):
    """
    A reference to another field (`this.name`, or a function of the context)
    could not be evaluated.
    """


def _shorten(value) -> str:
    """
    The repr of `value`, cut down to a length that fits in an error message.
    """

    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def attempt(func, value, *rest):
    """
    Call a user's function as `func(value, *rest)`, raising a `ValidationError`
    if it fails with anything other than a `PaboError`.

    Used wherever pabo calls a function the user gave it (`Adapted`'s decode
    and encode, predicates, checksum functions), so that every failure is a
    `PaboError` with the field's path, and `Greedy` stops on it like on any
    other error. The original exception is kept as the `__cause__`.

    Left unannotated, so beartype skips it: it runs once per value.
    """

    try:
        return func(value, *rest)
    except PaboError:
        raise
    except Exception as error:
        name = getattr(func, "__name__", type(func).__name__)
        raise ValidationError(
            f"THE FUNCTION {name} FAILED ON {_shorten(value)}: {_shorten(error)}."
        ) from error
