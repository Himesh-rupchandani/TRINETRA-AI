import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { IconTile, type TileTone } from '@/components/common/IconTile';
import { cn } from '@/lib/utils';

type Tone = 'neutral' | 'online' | 'critical' | 'brand' | 'warn';

const TONE_TO_TILE: Record<Tone, TileTone> = {
  neutral: 'slate',
  online: 'green',
  critical: 'red',
  brand: 'blue',
  warn: 'amber',
};

/** Soft card wash per tile tone — the same subtle family as the nav cards. */
const TILE_TINTS: Record<TileTone, string> = {
  blue: 'bg-gradient-to-br from-blue-100/70 via-blue-50/40 to-white',
  sky: 'bg-gradient-to-br from-sky-100/70 via-sky-50/40 to-white',
  green: 'bg-gradient-to-br from-emerald-100/70 via-emerald-50/40 to-white',
  orange: 'bg-gradient-to-br from-orange-100/70 via-orange-50/40 to-white',
  amber: 'bg-gradient-to-br from-amber-100/70 via-amber-50/40 to-white',
  purple: 'bg-gradient-to-br from-violet-100/70 via-violet-50/40 to-white',
  red: 'bg-gradient-to-br from-rose-100/70 via-rose-50/40 to-white',
  slate: '',
};

export function KpiCard({
  label,
  value,
  sub,
  tone = 'neutral',
  tile,
  icon: Icon,
  to,
  cta,
  loading,
  extra,
  className,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  tile?: TileTone;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  to?: string;
  cta?: string;
  loading?: boolean;
  /** Extra row between the sub-line and the link (chips, health bar…). */
  extra?: ReactNode;
  /** Positioning classes for the card wrapper (grid spans…). */
  className?: string;
}) {
  const resolvedTile = tile ?? TONE_TO_TILE[tone];
  const body = (
    <div
      className={cn(
        'panel relative flex h-full flex-col gap-2.5 overflow-hidden p-4 transition-shadow hover:shadow-cardHover',
        TILE_TINTS[resolvedTile],
      )}
    >
      <div className="flex items-center gap-2.5">
        {Icon && (
          <IconTile tone={resolvedTile} size="md">
            <Icon size={18} />
          </IconTile>
        )}
        <p className="min-w-0 text-xs font-semibold leading-snug text-ink-muted">{label}</p>
      </div>

      <div>
        {loading ? (
          <div className="skeleton h-8 w-16" />
        ) : (
          <p
            className={cn(
              'font-mono text-[1.75rem] font-bold leading-none tabular-nums',
              tone === 'critical' ? 'text-critical' : tone === 'warn' ? 'text-degraded' : 'text-ink',
            )}
          >
            {value}
          </p>
        )}
        {sub && <p className="mt-1.5 text-2xs leading-snug text-ink-faint">{sub}</p>}
      </div>

      {extra}
      {to && (
        <span className="mt-auto inline-flex items-center gap-1 pt-1 text-xs font-semibold text-brand">
          {cta ?? 'View'}
          <ArrowRight size={13} aria-hidden />
        </span>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} className={cn('block h-full focus-visible:rounded-2xl', className)}>
        {body}
      </Link>
    );
  }
  return className ? <div className={className}>{body}</div> : body;
}
