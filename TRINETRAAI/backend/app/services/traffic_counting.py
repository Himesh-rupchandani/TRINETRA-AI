"""Bounded observation-session counters, independent of plate recognition.

These are confirmed *track* counts, not a claim of complete/unique physical
traffic. Only real observations are evaluated. Lines/boxes use normalized
coordinates and frame PTS (or capture time), not assumed video FPS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrafficConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    mode: Literal["off", "line", "zone"] = "off"
    axis: Literal["horizontal", "vertical"] = "horizontal"
    direction: Literal["both", "positive", "negative"] = "both"
    position: float = Field(.5, ge=0, le=1)
    span_start: float = Field(.05, ge=0, le=1)
    span_end: float = Field(.95, ge=0, le=1)
    left: float = Field(.25, ge=0, le=1)
    top: float = Field(.25, ge=0, le=1)
    right: float = Field(.75, ge=0, le=1)
    bottom: float = Field(.75, ge=0, le=1)

    @model_validator(mode="after")
    def geometry(self):
        if self.span_end - self.span_start < .02 - 1e-9:
            raise ValueError("The counting line must have a non-zero span (at least 2%).")
        if self.right - self.left < .02 - 1e-9 or self.bottom - self.top < .02 - 1e-9:
            raise ValueError("The zone must have positive width and height (at least 2%).")
        return self


@dataclass
class Observation:
    point: tuple[float, float]
    time_s: float
    observed_counted: bool = False
    crossing_counted: bool = False
    side: int = 0
    anchor: tuple[float, float] | None = None
    inside: bool | None = None


def segment_enters_box(start, end, config):
    """Segment/interior intersection; also catches a skipped-over narrow zone."""
    low, high = 0.0, 1.0
    for a, b, minimum, maximum in zip(start, end, (config.left, config.top), (config.right, config.bottom)):
        delta = b - a
        if abs(delta) < 1e-9:
            if not minimum < a < maximum:
                return False
            continue
        t1, t2 = sorted(((minimum-a)/delta, (maximum-a)/delta))
        low, high = max(low, t1), min(high, t2)
        if low >= high:
            return False
    return high > low and high > 0 and low < 1


class TrafficCounter:
    def __init__(self, config=None, *, started_at=None, reason="started", revision="default"):
        self.config = config or TrafficConfig()
        self.session_id = uuid4().hex
        self.started_at = started_at
        self.reset_reason = reason
        self.revision = revision
        self._observations: dict[int, Observation] = {}
        self.observed = 0
        self.crossings = 0
        self.forward = 0
        self.reverse = 0
        self.other_direction = 0
        self.by_class = {name: 0 for name in ("car", "motorcycle", "bus", "truck")}
        self.crossings_by_class = dict(self.by_class)
        self.samples = 0
        self._first_time = None
        self._last_time = None
        self.visible = 0
        self.input_limited = False

    def update(self, tracks, time_s, width, height, *, max_gap, input_limited=False):
        self.samples += 1
        if self._first_time is None:
            self._first_time = time_s
        self._last_time = time_s
        self.input_limited = self.input_limited or input_limited
        observed = [track for track in tracks if track.misses == 0]
        self.visible = len(observed)
        # Retired track state never accumulates for the lifetime of a stream.
        active = {t.track_id for t in tracks}
        self._observations = {k: v for k, v in self._observations.items() if k in active}
        config = self.config
        coordinate = 1 if config.axis == "horizontal" else 0
        for track in observed:
            point = ((track.x1 + track.x2) / (2*width), (track.y1 + track.y2) / (2*height))
            old = self._observations.get(track.track_id)
            previous = old.point if old else None
            fresh_pair = old is not None and 0 < time_s - old.time_s <= max_gap
            if old is None:
                old = self._observations[track.track_id] = Observation(point, time_s)
            confirmed = track.hits >= 2
            name = track.class_name if track.class_name in self.by_class else None
            if confirmed and not old.observed_counted:
                self.observed += 1
                if name:
                    self.by_class[name] += 1
                old.observed_counted = True

            crossing = False
            delta = point[coordinate] - previous[coordinate] if previous else 0
            if config.mode == "line":
                distance = point[coordinate] - config.position
                side = 1 if distance > .010000001 else -1 if distance < -.010000001 else 0
                if side:
                    if fresh_pair and old.side and side != old.side and old.anchor:
                        a = old.anchor
                        fraction = (config.position-a[coordinate]) / (point[coordinate]-a[coordinate])
                        along = a[1-coordinate] + fraction * (point[1-coordinate]-a[1-coordinate])
                        crossing = config.span_start <= along <= config.span_end
                        delta = point[coordinate] - a[coordinate]
                    old.side, old.anchor = side, point
                elif not fresh_pair:
                    old.side, old.anchor = 0, None
            elif config.mode == "zone":
                # Hysteresis prevents tiny boundary jitter from counting entries.
                inside = (config.left+.005 < point[0] < config.right-.005 and
                          config.top+.005 < point[1] < config.bottom-.005)
                outside = (point[0] < config.left-.005 or point[0] > config.right+.005 or
                           point[1] < config.top-.005 or point[1] > config.bottom+.005)
                if fresh_pair and old.inside is False:
                    anchor = old.anchor or previous
                    crossing = inside or (outside and segment_enters_box(anchor, point, config))
                    delta = point[coordinate] - anchor[coordinate]
                if inside or outside or old.inside is None or not fresh_pair:
                    old.inside = inside if inside or outside else None
                    old.anchor = point if inside or outside else None

            accepted_direction = (config.direction == "both" or
                                  (config.direction == "positive" and delta > .005) or
                                  (config.direction == "negative" and delta < -.005))
            if crossing and confirmed and not old.crossing_counted and accepted_direction:
                old.crossing_counted = True
                self.crossings += 1
                if name:
                    self.crossings_by_class[name] += 1
                if delta > .005:
                    self.forward += 1
                elif delta < -.005:
                    self.reverse += 1
                else:
                    self.other_direction += 1
            old.point, old.time_s = point, time_s

    def snapshot(self):
        duration = (self._last_time - self._first_time) if self._first_time is not None else 0
        return dict(
            session_id=self.session_id, started_at=self.started_at, reset_reason=self.reset_reason,
            config=self.config.model_dump(), config_revision=self.revision,
            observed_tracks=self.observed, visible_vehicles=self.visible,
            crossings=self.crossings, forward=self.forward, reverse=self.reverse,
            other_direction=self.other_direction,
            by_class=dict(self.by_class), crossings_by_class=dict(self.crossings_by_class),
            samples=self.samples, sample_hz=round((self.samples-1)/duration, 2) if duration > 0 else None,
            input_limited=self.input_limited,
        )
