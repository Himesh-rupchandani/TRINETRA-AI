import type { Severity } from '@/types';

export { formatDateTime, formatTime, relativeTime, prettyPlate } from '@/lib/utils';

/**
 * Severity → presentation tokens. Three visual tiers (Critical / Warning
 * / Information) as per the design system — labels always accompany
 * colour, never colour alone.
 */
export const severityTone: Record<Severity, { text: string; bar: string; soft: string }> = {
  CRITICAL: { text: 'text-critical', bar: 'bg-critical', soft: 'bg-critical/[0.05] border-critical/25' },
  HIGH: { text: 'text-warn', bar: 'bg-warn', soft: 'bg-warn/[0.06] border-warn/25' },
  MEDIUM: { text: 'text-warn', bar: 'bg-warn', soft: 'bg-warn/[0.06] border-warn/25' },
  LOW: { text: 'text-info', bar: 'bg-info', soft: 'bg-surface-2 border-line-strong' },
  INFO: { text: 'text-info', bar: 'bg-info', soft: 'bg-surface-2 border-line-strong' },
};

export const severityHex: Record<Severity, string> = {
  CRITICAL: '#b3261e',
  HIGH: '#9a6700',
  MEDIUM: '#9a6700',
  LOW: '#5c5c57',
  INFO: '#5c5c57',
};

export const cameraStatusHex: Record<string, string> = {
  ONLINE: '#2e7d32',
  OFFLINE: '#b3261e',
  DEGRADED: '#9a6700',
};

/** ANPR confidence text tone. */
export function confidenceTone(c?: number | null): string {
  if (c == null) return 'text-ink-faint';
  const n = c <= 1 ? c * 100 : c;
  if (n >= 92) return 'text-online';
  if (n >= 80) return 'text-warn';
  return 'text-critical';
}

/** Human names for the event taxonomy (Vehicle Log, evidence, filters). */
export const EVENT_TYPE_LABELS: Record<string, string> = {
  VEHICLE_DETECTION: 'Vehicle detection',
  ANPR_READ: 'Plate read',
  WATCHLIST_MATCH: 'Wanted match',
  CAMERA_OFFLINE: 'Camera offline',
  CAMERA_RECOVERED: 'Camera recovered',
  SPEED_VIOLATION: 'Speed violation',
  WRONG_WAY: 'Wrong way',
};
