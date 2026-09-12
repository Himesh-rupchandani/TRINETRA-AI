import type { Severity, AlertStatus, CameraStatus, ServiceStatus } from '@/types';

/** Tailwind-safe class join (no external clsx dependency). */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

/* ----------------------------- formatting ----------------------------- */

export function formatTime(iso?: string): string {
  if (!iso) return '--:--:--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--:--';
  return d.toLocaleTimeString('en-GB', { hour12: false });
}

export function formatShortTime(iso?: string): string {
  if (!iso) return '--:--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--:--';
  return d.toLocaleTimeString('en-GB', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

export function formatDate(iso?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function formatDateTime(iso?: string): string {
  if (!iso) return '—';
  return `${formatDate(iso)} ${formatTime(iso)}`;
}

export function relativeTime(iso?: string, now: number = Date.now()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const s = Math.round((now - t) / 1000);
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes)) return '—';
  if (minutes > 0 && minutes < 1) return `${Math.max(1, Math.round(minutes * 60))}s`;
  const m = Math.round(minutes);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function formatPct(v?: number, digits = 0): string {
  if (v == null || Number.isNaN(v)) return '—';
  const n = v <= 1 ? v * 100 : v;
  return `${n.toFixed(digits)}%`;
}

export function formatNumber(n?: number): string {
  if (n == null) return '—';
  return n.toLocaleString('en-IN');
}

/** Position inside an uploaded CCTV video: 134s -> "00:02:14". */
export function formatVideoOffset(sec?: number | null): string {
  if (sec == null || Number.isNaN(sec)) return '—';
  const s = Math.max(0, Math.floor(sec));
  const h = String(Math.floor(s / 3600)).padStart(2, '0');
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const r = String(s % 60).padStart(2, '0');
  return `${h}:${m}:${r}`;
}

/** Normalises user plate input: strips spaces/hyphens, uppercases. */
export function normalisePlate(input: string): string {
  return input.toUpperCase().replace(/[^A-Z0-9]/g, '');
}

/**
 * Canonical Indian registration plate — ONE definition shared by every layer:
 *
 *   SS  DD  L{1,3}  N{3,4}     e.g. GJ 01 AB 1234, MH 02 CD 5678
 *
 * two state letters, RTO digits (two today, one on legacy plates), at least one
 * series letter and a 3-4 digit number.
 *
 * Must stay byte-identical to `CANONICAL_PLATE_PATTERN` in
 * TRINETRAAI/backend/app/utils/plate_normalizer.py and to cv-engine's
 * cv-engine/anpr/normalizer.py — the backend test
 * tests/test_plate_format_consistency.py fails if any layer drifts.
 *
 * The previous UI pattern allowed ZERO series letters and only ONE number
 * digit, so "GJ011234" and "GJ1A2" passed validation here while the backend
 * pipeline rejected the same strings, and prettyPlate happily rendered a
 * half-split "GJ 01 1234".
 */
export const INDIAN_PLATE_PATTERN = '^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$';
const INDIAN_PLATE_RE = new RegExp(INDIAN_PLATE_PATTERN);
const INDIAN_PLATE_GROUPS = /^([A-Z]{2})([0-9]{1,2})([A-Z]{1,3})([0-9]{3,4})$/;

/** Pretty print an Indian plate: GJ01AB1234 -> GJ 01 AB 1234 */
export function prettyPlate(plate: string): string {
  const p = normalisePlate(plate);
  const m = INDIAN_PLATE_GROUPS.exec(p);
  // Only a fully canonical plate is split into groups; anything else is shown
  // normalized (never half-split, never invented).
  return m ? `${m[1]} ${m[2].padStart(2, '0')} ${m[3]} ${m[4]}` : p || plate;
}

export function isValidPlate(input: string): boolean {
  return INDIAN_PLATE_RE.test(normalisePlate(input));
}

/* --------------------------- semantic colours --------------------------- */

export const severityClass: Record<Severity, string> = {
  CRITICAL: 'bg-critical/15 text-critical border-critical/45',
  HIGH: 'bg-high/15 text-high border-high/45',
  MEDIUM: 'bg-medium/15 text-medium border-medium/45',
  LOW: 'bg-low/15 text-low border-low/45',
  INFO: 'bg-info/15 text-info border-info/45',
};

export const severityBar: Record<Severity, string> = {
  CRITICAL: 'bg-critical',
  HIGH: 'bg-high',
  MEDIUM: 'bg-medium',
  LOW: 'bg-low',
  INFO: 'bg-info',
};

export const severityHex: Record<Severity, string> = {
  CRITICAL: '#e11d48',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#0ea5e9',
  INFO: '#64748b',
};

export const cameraStatusClass: Record<CameraStatus, string> = {
  ONLINE: 'bg-online/15 text-online border-online/45',
  OFFLINE: 'bg-offline/15 text-offline border-offline/45',
  DEGRADED: 'bg-degraded/15 text-degraded border-degraded/45',
  // Neutral, not red: nothing is broken, no source has been authorized yet.
  NOT_CONFIGURED: 'bg-surface-3 text-ink-muted border-line',
};

export const cameraStatusDot: Record<CameraStatus, string> = {
  ONLINE: 'bg-online',
  OFFLINE: 'bg-offline',
  DEGRADED: 'bg-degraded',
  NOT_CONFIGURED: 'bg-ink-faint',
};

export const cameraStatusHex: Record<CameraStatus, string> = {
  ONLINE: '#16a34a',
  OFFLINE: '#dc2626',
  DEGRADED: '#d97706',
  NOT_CONFIGURED: '#64748b',
};

export const alertStatusClass: Record<AlertStatus, string> = {
  NEW: 'bg-processing text-white border-processing',
  ACKNOWLEDGED: 'bg-processing/12 text-processing border-processing/30',
  RESOLVED: 'bg-online/12 text-online border-online/35',
};

export const serviceStatusClass: Record<ServiceStatus, string> = {
  HEALTHY: 'bg-online/15 text-online border-online/45',
  DEGRADED: 'bg-degraded/15 text-degraded border-degraded/45',
  OFFLINE: 'bg-offline/15 text-offline border-offline/45',
};

export function confidenceClass(c: number): string {
  const n = c <= 1 ? c * 100 : c;
  if (n >= 92) return 'text-online';
  if (n >= 80) return 'text-medium';
  return 'text-high';
}

/* ------------------------------- geo maths ------------------------------- */

export function haversineKm(
  a: { latitude: number; longitude: number },
  b: { latitude: number; longitude: number },
): number {
  const R = 6371;
  const dLat = ((b.latitude - a.latitude) * Math.PI) / 180;
  const dLon = ((b.longitude - a.longitude) * Math.PI) / 180;
  const la1 = (a.latitude * Math.PI) / 180;
  const la2 = (b.latitude * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.sin(dLon / 2) ** 2 * Math.cos(la1) * Math.cos(la2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

/* -------------------------------- misc -------------------------------- */

export function minutesBetween(a: string, b: string): number {
  return Math.abs(new Date(b).getTime() - new Date(a).getTime()) / 60000;
}

export function sortByTimeDesc<T extends { timestamp?: string; createdAt?: string }>(
  items: T[],
): T[] {
  return [...items].sort(
    (x, y) =>
      new Date(y.timestamp ?? y.createdAt ?? 0).getTime() -
      new Date(x.timestamp ?? x.createdAt ?? 0).getTime(),
  );
}

export function unique<T>(arr: T[]): T[] {
  return Array.from(new Set(arr));
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Plain-English name for each AI event type.
 * The API keeps machine codes (VEHICLE_DETECTION); officers see "Vehicle seen".
 */
export const eventTypeLabel: Record<string, string> = {
  VEHICLE_DETECTION: 'Vehicle seen',
  ANPR_READ: 'Number plate read',
  WATCHLIST_MATCH: 'Wanted vehicle found',
  CAMERA_OFFLINE: 'Camera stopped working',
  CAMERA_RECOVERED: 'Camera started working',
  SPEED_VIOLATION: 'Speeding',
  WRONG_WAY: 'Driving the wrong way',
};

/** Safe lookup that falls back to a readable version of the raw code. */
export function prettyEventType(type: string): string {
  return eventTypeLabel[type] ?? type.replace(/_/g, ' ').toLowerCase();
}

/** "AUTO_RICKSHAW" -> "Auto rickshaw" — readable vehicle type for officers. */
export function prettyVehicleClass(value?: string | null): string {
  if (!value) return '—';
  const words = value.replace(/_/g, ' ').toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
