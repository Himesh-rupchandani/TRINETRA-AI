import type { ReactNode } from 'react';
import { AlertOctagon, ChevronLeft, ChevronRight, Inbox, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './Button';

export function Spinner({ size = 14, className }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={cn('animate-spin text-current', className)} aria-hidden />;
}

/** Shimmer skeleton block. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton', className)} aria-hidden />;
}

/** Labelled skeleton rows for list/table loading states. */
export function LoadingRows({
  label = 'Loading',
  rows = 4,
  className,
}: {
  label?: string;
  rows?: number;
  className?: string;
}) {
  return (
    <div className={cn('p-5', className)} role="status" aria-live="polite" aria-busy="true">
      <p className="mb-3 flex items-center gap-2 text-xs font-medium text-ink-faint">
        <Spinner size={12} /> {label}…
      </p>
      <div className="space-y-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-9" />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  icon: Icon = Inbox,
  action,
  className,
}: {
  title: string;
  detail?: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-8 py-14 text-center', className)}>
      <span className="mb-1 grid h-11 w-11 place-items-center rounded-full border border-line bg-surface-2 text-ink-faint">
        <Icon size={18} aria-hidden />
      </span>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {detail && <p className="max-w-sm text-xs leading-relaxed text-ink-faint">{detail}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center gap-2 px-8 py-14 text-center', className)}
      role="alert"
    >
      <span className="mb-1 grid h-11 w-11 place-items-center rounded-full border border-critical/25 bg-critical/[0.06] text-critical">
        <AlertOctagon size={18} aria-hidden />
      </span>
      <p className="text-sm font-semibold text-ink">Something went wrong</p>
      <p className="max-w-sm text-xs leading-relaxed text-ink-muted">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

/** Renders loading / error / empty / content. */
export function Boundary({
  loading,
  error,
  isEmpty,
  onRetry,
  emptyTitle = 'Nothing here yet',
  emptyDetail,
  loadingLabel,
  className,
  children,
}: {
  loading: boolean;
  error?: string | null;
  isEmpty?: boolean;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDetail?: string;
  loadingLabel?: string;
  className?: string;
  children: ReactNode;
}) {
  if (loading) return <LoadingRows label={loadingLabel} className={className} />;
  if (error) return <ErrorState message={error} onRetry={onRetry} className={className} />;
  if (isEmpty) return <EmptyState title={emptyTitle} detail={emptyDetail} className={className} />;
  return <>{children}</>;
}

export function KeyVal({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-[11px] font-medium text-ink-faint">{label}</dt>
      <dd className="break-words text-[13px] font-medium text-ink">{children}</dd>
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (p: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <nav
      className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3"
      aria-label="Pagination"
    >
      <p className="text-xs text-ink-faint">
        Showing <span className="font-semibold text-ink-muted">{from}</span>–
        <span className="font-semibold text-ink-muted">{to}</span> of{' '}
        <span className="font-semibold text-ink-muted">{total.toLocaleString('en-IN')}</span>
      </p>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="xs" onClick={() => onPageChange(page - 1)} disabled={page <= 1} aria-label="Previous page">
          <ChevronLeft size={12} aria-hidden /> Prev
        </Button>
        <span className="mono text-xs text-ink-muted">
          {page} / {pages}
        </span>
        <Button variant="ghost" size="xs" onClick={() => onPageChange(page + 1)} disabled={page >= pages} aria-label="Next page">
          Next <ChevronRight size={12} aria-hidden />
        </Button>
      </div>
    </nav>
  );
}
