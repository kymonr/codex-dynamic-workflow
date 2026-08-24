"""Injectable absolute-clock support for whole-workflow deadlines."""

from __future__ import annotations

import asyncio
import time
from typing import Protocol


class DeadlineClock(Protocol):
    """Minimal clock contract used by the trusted scheduler."""

    def epoch_ms(self) -> int:
        """Return the current Unix epoch in milliseconds."""

    async def wait_until(self, deadline_epoch_ms: int) -> None:
        """Return when the supplied absolute deadline is reached."""


class SystemDeadlineClock:
    """Standard-library production clock implementation."""

    def epoch_ms(self) -> int:
        return time.time_ns() // 1_000_000

    async def wait_until(self, deadline_epoch_ms: int) -> None:
        remaining_ms = deadline_epoch_ms - self.epoch_ms()
        if remaining_ms <= 0:
            return
        monotonic_deadline_ns = time.monotonic_ns() + remaining_ms * 1_000_000
        while True:
            remaining_ns = monotonic_deadline_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                return
            await asyncio.sleep(remaining_ns / 1_000_000_000)


def checked_epoch_ms(clock: DeadlineClock) -> int:
    """Read a clock value while rejecting booleans and malformed clocks."""

    value = clock.epoch_ms()
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("deadline clock epoch_ms must be a non-negative integer")
    return value
