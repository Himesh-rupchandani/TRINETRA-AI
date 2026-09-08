import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Card family — white surface, hairline border, quiet shadow.
 * `interactive` adds the lift-on-hover / settle-on-press feel.
 */
export function Card({
  children,
  className,
  interactive = false,
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
}) {
  return (
    <section
      className={cn(
        'flex flex-col rounded-xl border border-line bg-surface-1 shadow-xs',
        interactive &&
          'transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md active:translate-y-0 active:scale-[0.995]',
        className,
      )}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        'flex min-h-[52px] flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-2.5',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="truncate text-sm font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 truncate text-xs text-ink-faint">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('min-h-0 flex-1', className)}>{children}</div>;
}

export function CardFooter({ children, className }: { children: ReactNode; className?: string }) {
  return <footer className={cn('border-t border-line px-5 py-3', className)}>{children}</footer>;
}

/** Section label used between page regions (small caps, quiet). */
export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-faint', className)}>
      {children}
    </p>
  );
}
