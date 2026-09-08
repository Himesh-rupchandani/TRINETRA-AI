import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Minus, TrendingDown, TrendingUp } from 'lucide-react';
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

const SPARK_TONE: Record<'brand' | 'accent' | 'critical' | 'online', string> = {
  brand: 'text-brand',
  accent: 'text-accent',
  critical: 'text-critical',
  online: 'text-online',
};

/** Dependency-free inline sparkline (cyan/amber/critical, area-filled). */
export function Sparkline({
  data,
  tone = 'brand',
  className,
}: {
  data: number[];
  tone?: keyof typeof SPARK_TONE;
  className?: string;
}) {
  if (data.length < 2) return <div className={cn('h-6', className)} aria-hidden />;
  const w = 120;
  const h = 26;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const span = max - min || 1;
  const x = (i: number) => (i / (data.length - 1)) * w;
  const y = (v: number) => h - 2 - ((v - min) / span) * (h - 4);
  const pts = data.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className={cn('h-6 w-full', SPARK_TONE[tone], className)}
      preserveAspectRatio="none"
      aria-hidden
    >
      <polygon
        points={`0,${h} ${pts.join(' ')} ${w},${h}`}
        className="fill-current opacity-[0.12]"
      />
      <polyline
        points={pts.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** Delta chip: "▲ +2 vs last hour" — tone decided by the caller. */
function DeltaChip({ delta, tone, label }: { delta: number; tone: 'good' | 'bad' | 'flat'; label: string }) {
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
  return (
    <span
      className={cn(
        'chip font-mono tabular-nums',
        tone === 'bad' && delta !== 0 && 'border-critical/45 bg-critical/10 text-critical',
        tone === 'good' && delta !== 0 && 'border-online/40 bg-online/10 text-online',
        (tone === 'flat' || delta === 0) && 'border-line bg-surface-3 text-ink-muted',
      )}
      title={`${delta >= 0 ? '+' : ''}${delta} ${label}`}
    >
      <Icon size={10} aria-hidden />
      {delta > 0 ? '+' : ''}
      {delta}
      <span className="font-sans font-medium normal-case tracking-normal opacity-75">{label}</span>
    </span>
  );
}

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
  spark,
  sparkTone = 'brand',
  delta,
  deltaTone,
  deltaLabel = 'vs last hr',
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
  /** Optional sparkline series (newest last). */
  spark?: number[];
  sparkTone?: 'brand' | 'accent' | 'critical' | 'online';
  /** Change vs the previous period; omit to hide the chip. */
  delta?: number;
  /** Whether an increase is good, bad, or neutral for this metric. */
  deltaTone?: 'good' | 'bad' | 'flat';
  deltaLabel?: string;
}) {
  const body = (
    <div className="panel card-hover relative flex h-full flex-col gap-2.5 overflow-hidden p-3.5">
      <div className="flex items-center justify-between gap-2.5">
        {Icon && (
          <IconTile tone={tile ?? TONE_TO_TILE[tone]} size="md">
            <Icon size={17} />
          </IconTile>
        )}
        <p className="min-w-0 text-right text-[11px] font-semibold uppercase leading-snug tracking-[0.06em] text-ink-faint">
          {label}
        </p>
      </div>

      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          {loading ? (
            <div className="skeleton h-8 w-16" />
          ) : (
            <p
              className={cn(
                'font-mono text-[1.65rem] font-bold leading-none tabular-nums',
                tone === 'warn' ? 'text-degraded' : 'text-ink',
              )}
            >
              {value}
            </p>
          )}
        </div>
        {!loading && delta != null && deltaTone && (
          <DeltaChip delta={delta} tone={deltaTone} label={deltaLabel} />
        )}
      </div>

      {loading ? (
        <div className="skeleton h-6 w-full" />
      ) : (
        spark && <Sparkline data={spark} tone={sparkTone} />
      )}

      {sub && <p className="text-2xs leading-snug text-ink-faint">{sub}</p>}

      {to && (
        <span className="mt-auto inline-flex items-center gap-1 text-xs font-semibold text-brand">
          {cta ?? 'View'}
          <ArrowRight size={13} aria-hidden />
        </span>
      )}
    </div>
  );

  return to ? (
    <Link to={to} className="block h-full focus-visible:rounded-xl">
      {body}
    </Link>
  ) : (
    body
  );
}
