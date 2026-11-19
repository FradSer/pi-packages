"""Shared terminal decoding for explicit native probes (uv --with pyte)."""
from __future__ import annotations


class TerminalFrames:
    def __init__(self, columns: int, lines: int) -> None:
        import pyte

        self._screen = pyte.Screen(columns, lines)
        self._stream = pyte.ByteStream(self._screen)
        self._pending = b""
        self.count = 0

    @property
    def display(self) -> list[str]:
        return self._screen.display

    def resize(self, columns: int, lines: int) -> None:
        self._screen.resize(columns=columns, lines=lines)

    def feed(self, data: bytes) -> None:
        self._pending += data
        # PTY reads can split a repaint. Only publish complete synchronized frames.
        end = b"\x1b[?2026l"
        while end in self._pending:
            frame, self._pending = self._pending.split(end, 1)
            self._stream.feed(frame + end)
            self.count += 1
