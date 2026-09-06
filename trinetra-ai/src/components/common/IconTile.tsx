import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Colored rounded-square icon tile — the visual signature of the design.
 * Used in the sidebar, page headers, KPI cards, hero and list rows.
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
  blue: 'bg-blue-500/12 text-blue-600',
  sky: 'bg-sky-500/12 text-sky-600',
  green: 'bg-emerald-500/12 text-emerald-600',
  orange: 'bg-orange-500/12 text-orange-600',
  amber: 'bg-amber-500/15 text-amber-600',
  purple: 'bg-violet-500/12 text-violet-600',
  red: 'bg-rose-500/12 text-rose-600',
  slate: 'bg-slate-500/12 text-slate-500',
};

/** Solid tile used for the active sidebar item. */
export const TILE_ACTIVE = 'bg-brand text-white shadow-sm';

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
