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
}) {
  const body = (
    <div className="panel relative flex h-full flex-col gap-3 overflow-hidden p-4 transition-shadow hover:shadow-cardHover">
      <div className="flex items-center justify-between gap-2.5">
        {Icon && (
          <IconTile tone={tile ?? TONE_TO_TILE[tone]} size="md">
            <Icon size={18} />
          </IconTile>
        )}
        <p className="min-w-0 text-right text-xs font-medium leading-snug text-ink-muted">{label}</p>
      </div>

      <div>
        {loading ? (
          <div className="skeleton h-8 w-16" />
        ) : (
          <p
            className={cn(
              'font-mono text-[1.75rem] font-bold leading-none tabular-nums',
              tone === 'warn' ? 'text-degraded' : 'text-ink',
            )}
          >
            {value}
          </p>
        )}
        {sub && <p className="mt-1.5 text-2xs leading-snug text-ink-faint">{sub}</p>}
      </div>

      {to && (
        <span className="mt-auto inline-flex items-center gap-1 text-xs font-semibold text-brand">
          {cta ?? 'View'}
          <ArrowRight size={13} aria-hidden />
        </span>
      )}
    </div>
  );

  return to ? (
    <Link to={to} className="block h-full focus-visible:rounded-2xl">
      {body}
    </Link>
  ) : (
    body
  );
}
