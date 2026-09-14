import type { ReactNode } from 'react';
import { Link, Outlet } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Focused workspace shell used by investigation screens
 * (vehicle trace, camera detail). Adds a case-context bar above the content.
 */
export function InvestigationLayout({
  backTo = '/',
  backLabel = 'Back to Command Center',
  title,
  status,
  meta,
  actions,
  children,
  className,
}: {
  backTo?: string;
  backLabel?: string;
  title?: ReactNode;
  status?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex h-full min-h-0 flex-col', className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2.5 border-b border-line bg-surface-1 px-4 py-3 sm:px-5">
        <Link to={backTo} className="btn-ghost btn-xs shrink-0">
          <ChevronLeft size={12} aria-hidden />
          <span className="hidden sm:inline">{backLabel}</span>
          <span className="sm:hidden">Back</span>
        </Link>
        {title && <div className="min-w-0">{title}</div>}
        {status}
        {meta && <div className="hidden items-center gap-3 md:flex">{meta}</div>}
        {actions && <div className="ml-auto flex flex-wrap items-center gap-1.5">{actions}</div>}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">{children ?? <Outlet />}</div>
    </div>
  );
}
