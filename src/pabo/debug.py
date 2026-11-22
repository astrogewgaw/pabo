"""
Debugging helpers.
"""

import sys
from dataclasses import dataclass, field
from typing import Any

from pabo.base import Construct, hexdump, tell


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
    file: Any = field(default=None, repr=False)

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
