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
    <div className={cn('animate-page-in flex h-full min-h-0 flex-col', className)}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-4 sm:px-6">
        <Link to={backTo} className="btn-ghost btn-xs shrink-0">
          <ChevronLeft size={12} aria-hidden />
          <span className="hidden sm:inline">{backLabel}</span>
          <span className="sm:hidden">Back</span>
        </Link>
        {title && <div className="min-w-0">{title}</div>}
        {status}
        {meta && <div className="hidden items-center gap-4 md:flex">{meta}</div>}
        {actions && <div className="ml-auto flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      <div className="min-h-0 flex-1 overflow-auto border-t border-line">{children ?? <Outlet />}</div>
    </div>
  );
}
