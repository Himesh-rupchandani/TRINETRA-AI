import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { AlertStatus, CameraStatus, Severity } from '@/types';
import { cn } from '@/lib/utils';

type Tone = 'neutral' | 'accent' | 'success' | 'warn' | 'danger' | 'info';

const TONES: Record<Tone, string> = {
  neutral: 'border-line-strong/60 bg-surface-2 text-ink-muted',
  accent: 'border-accent/25 bg-accent-weak text-accent-strong',
  success: 'border-online/25 bg-online/[0.07] text-online',
  warn: 'border-warn/25 bg-warn/[0.07] text-warn',
  danger: 'border-critical/25 bg-critical/[0.06] text-critical',
  info: 'border-line-strong/60 bg-surface-3 text-info',
};

/** Small quiet pill — the only badge shape in the product. */
export function Badge({
  tone = 'neutral',
  dot = false,
  pulse = false,
  className,
  children,
  title,
}: {
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-semibold leading-[16px]',
        TONES[tone],
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={cn(
            'h-1.5 w-1.5 rounded-full bg-current',
            pulse && 'animate-pulse-dot',
          )}
        />
      )}
      {children}
    </span>
  );
}

const CAMERA_TONE: Record<CameraStatus, { tone: Tone; label: string }> = {
  ONLINE: { tone: 'success', label: 'Online' },
  DEGRADED: { tone: 'warn', label: 'Degraded' },
  OFFLINE: { tone: 'danger', label: 'Offline' },
};

export function CameraStatusBadge({ status, className }: { status: CameraStatus; className?: string }) {
  const { tone, label } = CAMERA_TONE[status];
  return (
    <Badge tone={tone} dot pulse={status === 'ONLINE'} className={className} title={`Camera is ${label.toLowerCase()}`}>
      {label}
    </Badge>
  );
}

const SEVERITY_TONE: Record<Severity, Tone> = {
  CRITICAL: 'danger',
  HIGH: 'warn',
  MEDIUM: 'neutral',
  LOW: 'info',
  INFO: 'neutral',
};

const SEVERITY_LABEL: Record<Severity, string> = {
  CRITICAL: 'Critical',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  INFO: 'Info',
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <Badge tone={SEVERITY_TONE[severity]} className={className} title={`Priority: ${SEVERITY_LABEL[severity]}`}>
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}

const STATE_TONE: Record<AlertStatus, Tone> = {
  NEW: 'accent',
  ACKNOWLEDGED: 'info',
  RESOLVED: 'success',
};

const STATE_LABEL: Record<AlertStatus, string> = {
  NEW: 'New',
  ACKNOWLEDGED: 'Seen',
  RESOLVED: 'Closed',
};

export function AlertStateBadge({ status, className }: { status: AlertStatus; className?: string }) {
  return (
    <Badge tone={STATE_TONE[status]} className={className}>
      {STATE_LABEL[status]}
    </Badge>
  );
}

/** Plain-text link to a camera page, styled as data. */
export function CameraLink({ id, label, className }: { id: string; label?: string; className?: string }) {
  return (
    <Link
      to={`/cameras/${id}`}
      className={cn('mono text-ink-muted transition-colors hover:text-accent hover:underline', className)}
      title={`Open camera ${label ?? id}`}
    >
      {label ?? id.toUpperCase()}
    </Link>
  );
}
