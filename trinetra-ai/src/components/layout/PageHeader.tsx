import type { ReactNode } from 'react';
import { IconTile, type TileTone } from '@/components/common/IconTile';
import { cn } from '@/lib/utils';

/** Consistent page title row used across all top-level screens. */
export function PageHeader({
  title,
  subtitle,
  actions,
  className,
  icon: Icon,
  tone = 'blue',
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  tone?: TileTone;
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b border-line bg-surface-1 px-4 py-4 sm:px-5',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        {Icon && (
          <IconTile tone={tone} size="lg">
            <Icon size={20} />
          </IconTile>
        )}
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold leading-tight tracking-tight text-ink sm:text-2xl">
            {title}
          </h1>
          {subtitle && <div className="mt-0.5 text-sm leading-snug text-ink-muted">{subtitle}</div>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
