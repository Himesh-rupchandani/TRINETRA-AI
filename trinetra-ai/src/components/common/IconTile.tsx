import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Quiet icon container.
 *
 * The Atlas system deliberately dropped the old colored icon squares —
 * color is reserved for status and severity. This container is a neutral,
 * hairline tile used in the few places a bare icon needs structure.
 * The legacy `tone` prop is accepted for compatibility but renders neutral.
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
  blue: 'bg-surface-2 text-ink-muted',
  sky: 'bg-surface-2 text-ink-muted',
  green: 'bg-surface-2 text-ink-muted',
  orange: 'bg-surface-2 text-ink-muted',
  amber: 'bg-surface-2 text-ink-muted',
  purple: 'bg-surface-2 text-ink-muted',
  red: 'bg-surface-2 text-ink-muted',
  slate: 'bg-surface-2 text-ink-muted',
};

/** Kept for compatibility; equivalent to the neutral tile. */
export const TILE_ACTIVE = 'bg-surface-3 text-ink';

const SIZES = {
  sm: 'h-8 w-8 rounded-lg',
  md: 'h-9 w-9 rounded-lg',
  lg: 'h-10 w-10 rounded-lg',
  xl: 'h-11 w-11 rounded-xl',
} as const;

export function IconTile({
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
        'grid shrink-0 place-items-center border border-line bg-surface-2 text-ink-muted',
        SIZES[size],
        active && 'border-line-strong bg-surface-3 text-ink',
        className,
      )}
      aria-hidden
    >
      {children}
    </span>
  );
}
