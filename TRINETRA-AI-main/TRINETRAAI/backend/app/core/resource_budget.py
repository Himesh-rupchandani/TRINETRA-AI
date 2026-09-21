"""Best-effort container memory admission for the heavy CV stack.

A quota is not a throughput promise. The configured floor prevents loading
Torch + two detectors + OCR into a known undersized container. Runtime pressure
backs off inference rather than accumulating frames. API/native playback stay
available. Unknown limits are reported as unknown, never as verified capacity.
"""
from __future__ import annotations

from pathlib import Path
import threading
import time

from .config import settings

_MB = 1024 * 1024
_lock = threading.Lock()
_cached_at = float('-inf')
_cached = (None, None)


def _number(path):
    try:
        value = int(path.read_text().strip())
        return value if 0 < value < (1 << 60) else None
    except (OSError, ValueError):
        return None


def container_memory(root=Path('/sys/fs/cgroup')):
    """cgroup v2 or v1: capacity and working set (less reclaimable file cache)."""
    layouts = [(root/'memory.max',root/'memory.current',root/'memory.stat'),
               (root/'memory/memory.limit_in_bytes',root/'memory/memory.usage_in_bytes',root/'memory/memory.stat')]
    for limit_path, used_path, stat_path in layouts:
        limit = _number(limit_path)
        if limit is None:
            continue
        used = _number(used_path)
        inactive = 0
        try:
            stats = dict(line.split(maxsplit=1) for line in stat_path.read_text().splitlines())
            inactive = int(stats.get('inactive_file', stats.get('total_inactive_file','0')))
        except (OSError, ValueError):
            pass
        return limit, max(0, used-inactive) if used is not None else None
    return None, None


def memory_decision(limit, used, *, enabled=True, minimum_mb=1024, reserve_mb=160):
    state, reason = 'READY', None
    if not enabled:
        state = 'UNCHECKED'
    elif limit is None:
        state = 'UNKNOWN_LIMIT'
    elif limit < minimum_mb * _MB:
        state = 'INSUFFICIENT_MEMORY'
        reason = (f'AI paused: this container has {round(limit/_MB)} MB RAM; the configured safe '
                  f'minimum for this YOLO/OCR stack is {minimum_mb} MB. Use a larger ML backend. '
                  'The camera player is not waiting for inference.')
    elif used is not None and limit-used < reserve_mb * _MB:
        state = 'MEMORY_PRESSURE'
        reason = 'AI temporarily paused to protect playback/API: backend memory is nearly full. It will retry after pressure drops.'
    return dict(allowed=reason is None, state=state, reason=reason,
                limit_mb=round(limit/_MB) if limit is not None else None,
                working_set_mb=round(used/_MB) if used is not None else None,
                minimum_mb=minimum_mb, reserve_mb=reserve_mb,
                retry_after_ms=5000 if reason else 0)


def inference_budget():
    global _cached_at, _cached
    now = time.monotonic()
    with _lock:
        if now - _cached_at >= 1:
            _cached = container_memory()
            _cached_at = now
        limit, used = _cached
    return memory_decision(limit, used, enabled=settings.CV_MEMORY_GUARD_ENABLED,
                           minimum_mb=settings.CV_MIN_MEMORY_MB, reserve_mb=settings.CV_MEMORY_RESERVE_MB)
