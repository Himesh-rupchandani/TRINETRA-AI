import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';

type Tone = 'neutral' | 'online' | 'critical' | 'brand' | 'warn';

const TONE_VALUE: Record<Tone, string> = {
  neutral: 'text-ink',
  online: 'text-online',
  critical: 'text-critical',
  brand: 'text-ink',
  warn: 'text-degraded',
};

/**
 * Quiet stat card: label, value, context. No icon squares, no decoration —
 * the number is the interface.
 */
export function KpiCard({
  label,
  value,
  sub,
  tone = 'neutral',
  to,
  cta,
  loading,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  /** Legacy props from the previous design — accepted, not rendered. */
  tile?: unknown;
  icon?: unknown;
  to?: string;
  cta?: string;
  loading?: boolean;
}) {
  const body = (
    <div className="panel card-interactive relative flex h-full flex-col gap-3 p-5">
      <p className="text-xs font-medium text-ink-muted">{label}</p>
      <div>
        {loading ? (
          <div className="skeleton h-9 w-20" />
        ) : (
          <p
            className={cn(
              'font-mono text-[1.875rem] font-semibold leading-none tracking-tight tabular-nums',
              TONE_VALUE[tone],
            )}
          >
            {value}
          </p>
        )}
        {sub && <p className="mt-2.5 text-2xs leading-snug text-ink-faint">{sub}</p>}
      </div>

      {to && (
        <span className="mt-auto inline-flex items-center gap-1.5 pt-1 text-xs font-medium text-brand">
          {cta ?? 'View'}
          <ArrowRight size={13} aria-hidden />
        </span>
      )}
    </div>
  );

  return to ? (
    <Link to={to} className="block h-full rounded-xl focus-visible:outline-none [&:hover>div]:border-line-strong">
      {body}
    </Link>
  ) : (
    body
  );
}
