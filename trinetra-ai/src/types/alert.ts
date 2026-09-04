import type { Severity } from './vehicle';

export type AlertStatus = 'NEW' | 'ACKNOWLEDGED' | 'RESOLVED';

export interface Alert {
  id: string;
  eventId: string;
  plate: string;
  cameraId: string;
  cameraName?: string;
  /** Resolved from the camera registry when known. */
  location?: string;
  latitude?: number;
  longitude?: number;
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
