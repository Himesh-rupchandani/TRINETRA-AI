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

/** Pretty print an Indian plate: GJ01AB1234 -> GJ 01 AB 1234 */
export function prettyPlate(plate: string): string {
  const p = normalisePlate(plate);
  const m = /^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$/.exec(p);
  return m ? [m[1], m[2], m[3], m[4]].filter(Boolean).join(' ') : plate;
}

export function isValidPlate(input: string): boolean {
  return /^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}$/.test(normalisePlate(input));
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
  CRITICAL: '#FF3B5C',
  HIGH: '#FF8A3D',
  MEDIUM: '#FFC53D',
  LOW: '#38BDF8',
  INFO: '#94A3B8',
};

export const cameraStatusClass: Record<CameraStatus, string> = {
  ONLINE: 'bg-online/15 text-online border-online/45',
  OFFLINE: 'bg-offline/15 text-offline border-offline/45',
  DEGRADED: 'bg-degraded/15 text-degraded border-degraded/45',
};

export const cameraStatusDot: Record<CameraStatus, string> = {
  ONLINE: 'bg-online',
  OFFLINE: 'bg-offline',
  DEGRADED: 'bg-degraded',
};

export const cameraStatusHex: Record<CameraStatus, string> = {
  ONLINE: '#34D399',
  OFFLINE: '#F87171',
  DEGRADED: '#FBBF24',
};

export const alertStatusClass: Record<AlertStatus, string> = {
  NEW: 'bg-processing text-on-brand border-processing',
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
