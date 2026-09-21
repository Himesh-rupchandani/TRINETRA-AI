import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLive } from '@/features/alerts/LiveProvider';
import { useToast } from '@/features/system/ToastProvider';
import type { Severity } from '@/types';

const KIND: Record<Severity, 'error' | 'warning' | 'info'> = {
  CRITICAL: 'error',
  HIGH: 'error',
  MEDIUM: 'warning',
  LOW: 'info',
  INFO: 'info',
};

/**
 * Turns every live watchlist hit into a slide-in toast with a View link.
 * The red banner scrolls away with the page; these stay pinned to the
 * viewport, so an operator deep in a map or timeline still sees the hit.
 * Suppressed on /alerts itself — the feed there updates live anyway.
 */
export function LiveAlertToaster() {
  const { latestAlert } = useLive();
  const toast = useToast();
  const navigate = useNavigate();
  const toasted = useRef(new Set<string>());

  useEffect(() => {
    if (!latestAlert || toasted.current.has(latestAlert.id)) return;
    toasted.current.add(latestAlert.id);
    const a = latestAlert;
    const cat = a.category ? `${a.category}` : 'Watchlist match';
    const detail =
      `${cat} • ${a.cameraName ?? a.cameraId} • ${a.location}` +
      (a.confidence != null ? ` (${a.confidence.toFixed(1)}% match)` : '');
    toast.push(KIND[a.severity] ?? 'info', `🚨 Alert · ${a.plate}`, detail, {
      durationMs: 12_000,
      action: {
        label: '📍 View on Map',
        onClick: () => navigate(`/gis?focus=${a.cameraId.toLowerCase()}`),
      },
    });
  }, [latestAlert, toast, navigate]);

  return null;
}
