import type { Severity } from './vehicle';

export type AlertStatus = 'NEW' | 'ACKNOWLEDGED' | 'RESOLVED';

export interface Alert {
  id: string;
  eventId: string;
  plate: string;
  cameraId: string;
  cameraName?: string;
  location: string;
  /** Null when the camera has no known real-world position. */
  latitude?: number | null;
  longitude?: number | null;
  severity: Severity;
  status: AlertStatus;
  category: string;
  createdAt: string;
  confidence?: number;
  acknowledgedBy?: string;
  acknowledgedAt?: string;
  resolvedAt?: string;
  note?: string;
  evidenceRef?: string;
}

export interface AlertFilters {
  status?: AlertStatus | 'ALL';
  severity?: Severity | 'ALL';
  query?: string;
}
