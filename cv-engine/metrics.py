"""Performance measurement.

Rule from the integration spec: *do not fake metrics*. Every number here is read
from a real counter (``perf_counter``, ``psutil``, ``torch.cuda``). Where a metric
is genuinely unavailable (no GPU), it is reported as ``None``/``"unavailable"``
rather than fabricated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import psutil

    _HAVE_PSUTIL = True
except Exception:  # noqa: BLE001
    psutil = None
    _HAVE_PSUTIL = False


class Timer:
    """Accumulates wall durations of a stage (capture/infer/track/anpr/...)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.count = 0
        self.total_s = 0.0
        self.max_s = 0.0

    def __call__(self, seconds: float) -> None:
        self.count += 1
        self.total_s += seconds
        self.max_s = max(self.max_s, seconds)

    @property
    def avg_ms(self) -> float:
        return (self.total_s / self.count * 1000.0) if self.count else 0.0

    @property
    def max_ms(self) -> float:
        return self.max_s * 1000.0


@dataclass
class MetricsCollector:
    timers: dict[str, Timer] = field(default_factory=dict)
    events_per_minute_window_s: float = 60.0
    _event_times: list[float] = field(default_factory=list)

    def timer(self, name: str) -> Timer:
        if name not in self.timers:
            self.timers[name] = Timer(name)
        return self.timers[name]

    def record_event(self) -> None:
        now = time.monotonic()
        self._event_times.append(now)
        # Keep the window bounded.
        cutoff = now - self.events_per_minute_window_s
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.pop(0)

    @property
    def events_per_minute(self) -> float:
        return float(len(self._event_times))

    def resource_snapshot(self) -> dict:
        snap: dict = {
            "cpu_percent": None,
            "memory_used_mb": None,
            "memory_percent": None,
            "gpu_available": False,
            "gpu_utilization_percent": None,
            "gpu_memory_used_mb": None,
        }
        if _HAVE_PSUTIL:
            process = psutil.Process()
            snap["cpu_percent"] = process.cpu_percent(interval=None)
            snap["memory_used_mb"] = round(process.memory_info().rss / (1024 * 1024), 1)
            snap["memory_percent"] = round(process.memory_percent(), 1)
        try:
            import torch

            if torch.cuda.is_available():
                snap["gpu_available"] = True
                try:
                    snap["gpu_utilization_percent"] = round(torch.cuda.utilization(), 1)
                except Exception:  # noqa: BLE001
                    snap["gpu_utilization_percent"] = None
                snap["gpu_memory_used_mb"] = round(
                    torch.cuda.memory_allocated() / (1024 * 1024), 1
                )
        except Exception:  # noqa: BLE001
            pass
        return snap

    def summary(self) -> dict:
        return {
            "stages": {
                name: {
                    "count": t.count,
                    "avg_ms": round(t.avg_ms, 2),
                    "max_ms": round(t.max_ms, 2),
                }
                for name, t in self.timers.items()
            },
            "events_per_minute": self.events_per_minute,
            "resources": self.resource_snapshot(),
        }
