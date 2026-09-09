import { useCallback, useEffect, useRef, useState } from 'react';
import type { Marker as LeafletMarker } from 'leaflet';
import type { RoutePoint } from '@/types';

/** Screen time per route leg — every stop gets its moment. */
const LEG_MS = 1600;

function lerp(a: number, b: number, t: number): number {
  const s = t * t * (3 - 2 * t); // smoothstep: eases in and out of every stop
  return a + (b - a) * s;
}

/**
 * Drives the route-replay dot: a requestAnimationFrame loop moves a Leaflet
 * marker along the route legs and reports each reached stop so the timeline
 * can highlight in sync. Position and progress update via refs (no 60fps
 * re-renders); only play state and the current stop flow through React.
 */
export function useRoutePlayback(points: RoutePoint[], onStop?: (p: RoutePoint) => void) {
  const markerRef = useRef<LeafletMarker | null>(null);
  const barRef = useRef<HTMLDivElement | null>(null);
  const rafRef = useRef(0);
  const t0Ref = useRef(0);
  const elapsedRef = useRef(0);
  const legRef = useRef(-1);
  const pointsRef = useRef(points);
  pointsRef.current = points;
  const onStopRef = useRef(onStop);
  onStopRef.current = onStop;

  const [playing, setPlaying] = useState(false);
  const [started, setStarted] = useState(false);
  const [stopIndex, setStopIndex] = useState(0);

  const paint = useCallback((elapsed: number) => {
    const pts = pointsRef.current;
    const legs = Math.max(pts.length - 1, 1);
    const total = legs * LEG_MS;
    const clamped = Math.min(Math.max(elapsed, 0), total);
    const legFloat = clamped / LEG_MS;
    const legIdx = Math.min(Math.floor(legFloat), pts.length - 2);
    const frac = Math.min(Math.max(legFloat - legIdx, 0), 1);
    markerRef.current?.setLatLng([
      lerp(pts[legIdx].latitude, pts[legIdx + 1].latitude, frac),
      lerp(pts[legIdx].longitude, pts[legIdx + 1].longitude, frac),
    ]);
    if (barRef.current) barRef.current.style.width = `${(clamped / total) * 100}%`;
    // Report each stop once, as the dot arrives.
    const arrived = Math.min(Math.floor(legFloat + 1e-6), pts.length - 1);
    if (arrived !== legRef.current) {
      legRef.current = arrived;
      setStopIndex(arrived);
      onStopRef.current?.(pts[arrived]);
    }
  }, []);

  const loop = useCallback(() => {
    const legs = Math.max(pointsRef.current.length - 1, 1);
    const elapsed = elapsedRef.current + (performance.now() - t0Ref.current);
    paint(elapsed);
    if (elapsed < legs * LEG_MS) {
      rafRef.current = requestAnimationFrame(loop);
    } else {
      setPlaying(false);
    }
  }, [paint]);

  const play = useCallback(() => {
    if (pointsRef.current.length < 2) return;
    t0Ref.current = performance.now();
    setPlaying(true);
    rafRef.current = requestAnimationFrame(loop);
  }, [loop]);

  const pause = useCallback(() => {
    elapsedRef.current += performance.now() - t0Ref.current;
    cancelAnimationFrame(rafRef.current);
    setPlaying(false);
  }, []);

  const toggle = useCallback(() => {
    if (playing) {
      pause();
      return;
    }
    if (!started || elapsedRef.current >= Math.max(pointsRef.current.length - 1, 1) * LEG_MS) {
      // Fresh run (or replay after finishing): rewind first.
      elapsedRef.current = 0;
      legRef.current = -1;
      setStopIndex(0);
      setStarted(true);
    }
    play();
  }, [playing, started, pause, play]);

  const reset = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    elapsedRef.current = 0;
    legRef.current = -1;
    if (barRef.current) barRef.current.style.width = '0%';
    setPlaying(false);
    setStarted(false);
    setStopIndex(0);
  }, []);

  // A new route rewinds the replay.
  const routeKey = points.map((p) => p.eventId).join('|');
  useEffect(() => {
    reset();
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey]);

  useEffect(() => () => cancelAnimationFrame(rafRef.current), []);

  return { markerRef, barRef, playing, started, stopIndex, toggle, reset };
}
