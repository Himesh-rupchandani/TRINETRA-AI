import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Page title block — calm and typographic. No background bar, no icon tile:
 * the page opens with air, and the panels below carry the structure.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
  /** Deprecated in the Atlas system — accepted for compatibility, not rendered. */
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  tone?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-end justify-between gap-x-6 gap-y-4 px-1 pb-2 pt-1',
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="truncate text-xl font-semibold tracking-tight text-ink sm:text-2xl">
          {title}
        </h1>
        {subtitle && <div className="mt-1.5 text-sm leading-relaxed text-ink-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </div>
  );
}
