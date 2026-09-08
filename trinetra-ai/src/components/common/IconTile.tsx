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
  blue: 'bg-blue-500/15 text-blue-300',
  sky: 'bg-sky-500/15 text-sky-300',
  green: 'bg-emerald-500/15 text-emerald-300',
  orange: 'bg-orange-500/15 text-orange-300',
  amber: 'bg-amber-500/18 text-amber-300',
  purple: 'bg-violet-500/15 text-violet-300',
  red: 'bg-rose-500/15 text-rose-300',
  slate: 'bg-slate-500/15 text-slate-300',
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
