import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Shared investigation page frame — back link, identity block, status
 * chip, meta and actions. Keeps every case page structurally identical.
 */
export function InvestigationLayout({
  backTo,
  backLabel,
  title,
  status,
  meta,
  actions,
  children,
  className,
}: {
  backTo: string;
  backLabel: string;
  title: ReactNode;
  status?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('p-4 sm:p-6 lg:p-8', className)}>
      <Link
        to={backTo}
        className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted transition-colors hover:text-accent"
      >
        <ChevronLeft size={13} aria-hidden /> {backLabel}
      </Link>

      <header className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-line pb-4">
        <div className="flex min-w-0 flex-wrap items-center gap-x-3.5 gap-y-2">
          <h2 className="text-lg font-bold text-ink">{title}</h2>
          {status}
          {meta && <span className="text-xs text-ink-faint">{meta}</span>}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </header>

      <div className="mt-5">{children}</div>
    </div>
  );
}
