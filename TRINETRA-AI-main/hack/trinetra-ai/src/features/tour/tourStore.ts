/**
 * Tiny observable store for the guided walkthrough (no context needed —
 * the Header button opens it, the Tour overlay reads it).
 */
import { useSyncExternalStore } from 'react';

export interface TourState {
  open: boolean;
  i: number;
}

let snap: TourState = { open: false, i: 0 };
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((fn) => fn());

export const tourStore = {
  start(i = 0) {
    snap = { open: true, i };
    emit();
  },
  go(i: number) {
    snap = { ...snap, i };
    emit();
  },
  next(total: number) {
    if (snap.i >= total - 1) {
      tourStore.stop();
      return;
    }
    snap = { ...snap, i: snap.i + 1 };
    emit();
  },
  prev() {
    if (snap.i === 0) return;
    snap = { ...snap, i: snap.i - 1 };
    emit();
  },
  stop() {
    snap = { ...snap, open: false };
    try {
      // Once seen, never auto-play again (demo machines stay quiet).
      localStorage.setItem('trinetra-tour', 'seen');
    } catch {
      /* private mode */
    }
    emit();
  },
  subscribe(fn: () => void) {
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  },
  get: () => snap,
};

export function useTour(): TourState {
  return useSyncExternalStore(tourStore.subscribe, tourStore.get, tourStore.get);
}
