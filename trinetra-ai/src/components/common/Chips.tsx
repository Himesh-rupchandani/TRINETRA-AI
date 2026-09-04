import type { AlertStatus, CameraStatus, ServiceStatus, Severity } from '@/types';
import {
  alertStatusClass,
  cameraStatusClass,
  cameraStatusDot,
  cn,
  serviceStatusClass,
  severityClass,
} from '@/lib/utils';

/** Plain-English wording for every status the UI shows an officer. */
const CAMERA_LABEL: Record<CameraStatus, string> = {
  ONLINE: 'Working',
  DEGRADED: 'Poor quality',
  OFFLINE: 'Not working',
};

const SERVICE_LABEL: Record<ServiceStatus, string> = {
  HEALTHY: 'Working',
  DEGRADED: 'Needs attention',
  OFFLINE: 'Not working',
};

const ALERT_LABEL: Record<AlertStatus, string> = {
  NEW: 'New',
  ACKNOWLEDGED: 'Seen',
  RESOLVED: 'Closed',
};

const SEVERITY_LABEL: Record<Severity, string> = {
  CRITICAL: 'Urgent',
  HIGH: 'High priority',
  MEDIUM: 'Medium',
  LOW: 'Low',
  INFO: 'Routine',
};


export function SeverityChip({
  severity,
  className,
}: {
  /** Absent for live watchlist records the backend does not rate — shown as UNRATED. */
  severity: Severity | undefined;
  className?: string;
}) {
  return (
    <span
      className={cn('chip uppercase tracking-wide', (severity && severityClass[severity]) || 'bg-surface-2 text-ink-muted', className)}
      title={`Priority: ${severity ? (SEVERITY_LABEL[severity] ?? severity) : 'Not rated'}`}
    >
      {severity ? (SEVERITY_LABEL[severity] ?? severity) : 'Unrated'}
    </span>
  );
}

export function StatusChip({
  status,
  className,
  showDot = true,
}: {
  status: CameraStatus;
  className?: string;
  showDot?: boolean;
}) {
  return (
    <span className={cn('chip', cameraStatusClass[status], className)}>
      {showDot && (
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            cameraStatusDot[status],
            status === 'ONLINE' && 'animate-pulse',
          )}
          aria-hidden
        />
      )}
      {CAMERA_LABEL[status] ?? status}
    </span>
  );
}

export function AlertStatusChip({ status }: { status: AlertStatus }) {
  return (
    <span className={cn('chip uppercase tracking-wide', alertStatusClass[status])}>
      {ALERT_LABEL[status] ?? status}
    </span>
  );
}

export function ServiceStatusChip({ status }: { status: ServiceStatus }) {
  return (
    <span className={cn('chip', serviceStatusClass[status])}>{SERVICE_LABEL[status] ?? status}</span>
  );
}

export function Chip({
  children,
  tone = 'neutral',
  className,
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'brand' | 'warn';
  className?: string;
}) {
  const tones = {
    neutral: 'border-line bg-surface-3 text-ink-muted',
    brand: 'border-brand/45 bg-brand/10 text-brand',
    warn: 'border-degraded/45 bg-degraded/10 text-degraded',
  };
  return <span className={cn('chip', tones[tone], className)}>{children}</span>;
}
