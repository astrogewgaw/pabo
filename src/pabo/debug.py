"""
Debugging helpers.
"""

import sys
from dataclasses import dataclass, field

from pabo.base import Construct, hexdump, tell
from pabo.errors import PaboError
from pabo.hints import Writable


@dataclass
class Probe(Construct):
    """
    Print the stream position, the context and the next bytes. Takes no bytes.

    Put it anywhere in a specification while working out a format. `lookahead`
    bytes are shown (without consuming them) when parsing. Output goes to
    `file`, or stderr.
    """

    name: str = ""
    lookahead: int = 16
    file: Writable | None = field(default=None, repr=False)

    def __post_init__(self):
        if self.file is not None and not hasattr(self.file, "write"):
            raise PaboError(f"CANNOT PRINT TO {self.file!r}: IT HAS NO WRITE METHOD.")

    def _omittable(self):
        return True

    def _size(self, ctx):
        return 0

    def _report(self, stream, ctx, action: str) -> None:
        out = self.file or sys.stderr
        position = tell(stream)
        label = f" {self.name!r}" if self.name else ""
        print(f"Probe{label} while {action}, at offset {position}:", file=out)
        print(f"  context: {dict(ctx)!r}", file=out)
        if action == "parsing" and position is not None and self.lookahead:
            upcoming = stream.read(self.lookahead)
            stream.seek(position)
            print(f"  next {len(upcoming)} bytes:", file=out)
            for line in hexdump(upcoming, position).splitlines():
                print(f"    {line}", file=out)

    def _build(self, data, stream, ctx):
        self._report(stream, ctx, "building")
        return None

    def _parse(self, stream, ctx):
        self._report(stream, ctx, "parsing")
        return None


@dataclass
class Debug(Construct):
    """
    `wraps`, opening the Python debugger (pdb) where it fails.

    If parsing or building `wraps` raises an exception, `pdb.post_mortem` is
    started at the point of failure (the context is the `ctx` of the frames
    there), and the exception is raised again once you leave the debugger.
    """

    wraps: Construct

    def _omittable(self):
        return self.wraps._omittable()

    def _size(self, ctx):
        return self.wraps._size(ctx)

    def _debug(self, error: BaseException) -> None:
        import pdb

        print(f"pabo: {error}", file=sys.stderr)
        pdb.post_mortem(error.__traceback__)

    def _build(self, data, stream, ctx):
        try:
            return self.wraps._build(data, stream, ctx)
        except Exception as error:
            self._debug(error)
            raise

    def _parse(self, stream, ctx):
        try:
            return self.wraps._parse(stream, ctx)
        except Exception as error:
            self._debug(error)
            raise
