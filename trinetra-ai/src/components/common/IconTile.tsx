import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Colored rounded-square icon tile — the visual signature of the design.
 * Used in the sidebar, page headers, KPI cards, hero and list rows.
 * Tones are dark-tuned: translucent 400-level wells with 300-level ink.
 */
export type TileTone =
  | 'blue'
  | 'sky'
  | 'green'
  | 'orange'
  | 'amber'
  | 'purple'
  | 'red'
  | 'slate';

export const TILE_TONES: Record<TileTone, string> = {
  blue: 'bg-cyan-400/10 text-cyan-300 border border-cyan-400/15',
  sky: 'bg-sky-400/10 text-sky-300 border border-sky-400/15',
  green: 'bg-emerald-400/10 text-emerald-300 border border-emerald-400/15',
  orange: 'bg-orange-400/10 text-orange-300 border border-orange-400/15',
  amber: 'bg-amber-400/10 text-amber-300 border border-amber-400/15',
  purple: 'bg-violet-400/10 text-violet-300 border border-violet-400/15',
  red: 'bg-rose-400/10 text-rose-300 border border-rose-400/15',
  slate: 'bg-slate-400/10 text-slate-300 border border-slate-400/15',
};

/** Solid tile used for the active sidebar item. */
export const TILE_ACTIVE = 'bg-brand text-on-brand border border-brand shadow-glow';

const SIZES = {
  sm: 'h-8 w-8 rounded-lg',
  md: 'h-9 w-9 rounded-lg',
  lg: 'h-10 w-10 rounded-xl',
  xl: 'h-11 w-11 rounded-xl',
} as const;

export function IconTile({
  tone = 'slate',
  size = 'md',
  active = false,
  className,
  children,
}: {
  tone?: TileTone;
  size?: keyof typeof SIZES;
  active?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        'grid shrink-0 place-items-center',
        SIZES[size],
        active ? TILE_ACTIVE : TILE_TONES[tone],
        className,
      )}
      aria-hidden
    >
      {children}
    </span>
  );
}
