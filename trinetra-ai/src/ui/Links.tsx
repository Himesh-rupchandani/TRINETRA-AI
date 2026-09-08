import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { cn, prettyPlate } from '@/lib/utils';

/** Every plate in the product is a one-click entry into an investigation. */
export function PlateLink({
  plate,
  size = 'sm',
  pretty = false,
  className,
}: {
  plate: string;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  pretty?: boolean;
  className?: string;
}) {
  if (!plate || plate === '—') {
    return <span className="plate text-ink-faint">—</span>;
  }
  const sizes = { xs: 'text-xs', sm: 'text-[13px]', md: 'text-sm', lg: 'text-base' };
  return (
    <Link
      to={`/vehicles/${plate}`}
      title={`Trace ${plate}`}
      className={cn(
        'plate group inline-flex items-center gap-1 rounded px-0.5 -mx-0.5 text-ink transition-colors hover:text-accent',
        sizes[size],
        className,
      )}
    >
      {pretty ? prettyPlate(plate) : plate}
      <Search size={10} className="opacity-0 transition-opacity group-hover:opacity-70" aria-hidden />
    </Link>
  );
}

/** ANPR confidence: tiny meter + numeric value. */
export function ConfidenceMeter({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, value <= 1 ? value * 100 : value));
  const bar = pct >= 92 ? 'bg-online' : pct >= 80 ? 'bg-medium' : 'bg-high';
  const text = pct >= 92 ? 'text-online' : pct >= 80 ? 'text-medium' : 'text-high';
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className="h-1 w-12 overflow-hidden rounded-full bg-surface-3" aria-hidden>
        <span className={cn('block h-full rounded-full transition-[width] duration-500', bar)} style={{ width: `${pct}%` }} />
      </span>
      <span className={cn('mono text-xs tabular-nums', text)}>{pct.toFixed(0)}%</span>
    </span>
  );
}

/** Inline stat — label above, value below, used in status bands and cards. */
export function Stat({
  label,
  value,
  sub,
  to,
  tone = 'default',
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  to?: string;
  tone?: 'default' | 'danger';
  className?: string;
}) {
  const body = (
    <div
      className={cn(
        'flex min-w-0 flex-col gap-1 rounded-lg px-4 py-3.5 transition-colors duration-150',
        to && 'hover:bg-surface-2 active:bg-surface-3/70',
        className,
      )}
    >
      <p className="text-xs font-medium text-ink-muted">{label}</p>
      <p
        className={cn(
          'mono text-[22px] font-semibold leading-none tracking-tight',
          tone === 'danger' ? 'text-critical' : 'text-ink',
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-[11px] leading-snug text-ink-faint">{sub}</p>}
    </div>
  );
  return to ? (
    <Link to={to} className="rounded-lg focus-visible:outline-none">
      {body}
    </Link>
  ) : (
    body
  );
}
