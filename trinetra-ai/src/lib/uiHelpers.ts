import type { EventType, Severity } from '@/types';

export { formatDateTime, formatTime, relativeTime, prettyPlate } from '@/lib/utils';

/**
 * Severity → presentation tokens used across the new UI.
 * One source of truth for chip tones, bars and marker colors.
 */
export const severityTone: Record<Severity, { text: string; bar: string; soft: string }> = {
  CRITICAL: { text: 'text-critical', bar: 'bg-critical', soft: 'bg-critical/[0.06] border-critical/25' },
  HIGH: { text: 'text-high', bar: 'bg-high', soft: 'bg-high/[0.06] border-high/25' },
  MEDIUM: { text: 'text-medium', bar: 'bg-medium', soft: 'bg-medium/[0.08] border-medium/25' },
  LOW: { text: 'text-low', bar: 'bg-low', soft: 'bg-low/[0.06] border-low/25' },
  INFO: { text: 'text-info', bar: 'bg-info', soft: 'bg-surface-2 border-line-strong' },
};

export const severityHex: Record<Severity, string> = {
  CRITICAL: '#be123c',
  HIGH: '#c2410c',
  MEDIUM: '#a16207',
  LOW: '#0369a1',
  INFO: '#64748b',
};

export const cameraStatusHex: Record<string, string> = {
  ONLINE: '#16a34a',
  OFFLINE: '#dc2626',
  DEGRADED: '#b45309',
};

/** ANPR confidence text tone. */
export function confidenceTone(c?: number | null): string {
  if (c == null) return 'text-ink-faint';
  const n = c <= 1 ? c * 100 : c;
  if (n >= 92) return 'text-online';
  if (n >= 80) return 'text-medium';
  return 'text-high';
}

/** Human names for the event taxonomy (Vehicle Log, evidence, filters). */
export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  VEHICLE_DETECTION: 'Vehicle detection',
  ANPR_READ: 'Plate read',
  WATCHLIST_MATCH: 'Wanted match',
  CAMERA_OFFLINE: 'Camera offline',
  CAMERA_RECOVERED: 'Camera recovered',
  SPEED_VIOLATION: 'Speed violation',
  WRONG_WAY: 'Wrong way',
};
