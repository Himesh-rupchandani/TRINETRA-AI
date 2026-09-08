import type { ReactNode } from 'react';
import { AlertOctagon, Inbox, Loader2, RefreshCcw } from 'lucide-react';
import { cn } from '@/lib/utils';

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
  icon: Icon,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
}) {
  return (
    <section className={cn('panel flex min-h-0 flex-col overflow-hidden', className)}>
      {title && (
        <header className="panel-header">
          <h2 className="panel-title flex items-center gap-2.5">
            {Icon && <Icon size={15} className="text-ink-faint" aria-hidden />}
            {title}
          </h2>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn('min-h-0 flex-1', bodyClassName)}>{children}</div>
    </section>
  );
}

export function LoadingState({ label = 'Loading', rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="p-6" role="status" aria-live="polite" aria-busy="true">
      <div className="mb-4 flex items-center gap-2 text-2xs font-medium text-ink-faint">
        <Loader2 size={12} className="animate-spin" aria-hidden />
        {label}…
      </div>
      <div className="space-y-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton h-9" style={{ opacity: 1 - i * 0.14 }} />
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
}: {
  title: string;
  detail?: string;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-full min-h-[180px] flex-col items-center justify-center gap-3 p-10 text-center">
      <span className="mb-1 grid h-11 w-11 place-items-center rounded-full border border-line bg-surface-2 text-ink-faint">
        <Icon size={18} aria-hidden />
      </span>
      <p className="text-sm font-semibold text-ink">{title}</p>
      {detail && <p className="max-w-sm text-2xs leading-relaxed text-ink-faint">{detail}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex h-full min-h-[180px] flex-col items-center justify-center gap-3 p-10 text-center" role="alert">
      <span className="mb-1 grid h-11 w-11 place-items-center rounded-full border border-critical/25 bg-critical/10 text-critical">
        <AlertOctagon size={18} aria-hidden />
      </span>
      <p className="text-sm font-semibold text-critical">Request failed</p>
      <p className="max-w-sm text-2xs text-ink-muted">{message}</p>
      {onRetry && (
        <button type="button" className="btn-ghost btn-xs mt-2" onClick={onRetry}>
          <RefreshCcw size={11} aria-hidden /> Retry
        </button>
      )}
    </div>
  );
}

/** Renders loading / error / empty / content in one place. */
export function AsyncBoundary({
  loading,
  error,
  isEmpty,
  onRetry,
  emptyTitle = 'No records',
  emptyDetail,
  loadingLabel,
  children,
}: {
  loading: boolean;
  error?: string | null;
  isEmpty?: boolean;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDetail?: string;
  loadingLabel?: string;
  children: ReactNode;
}) {
  if (loading) return <LoadingState label={loadingLabel} />;
  if (error) return <ErrorState message={error} onRetry={onRetry} />;
  if (isEmpty) return <EmptyState title={emptyTitle} detail={emptyDetail} />;
  return <>{children}</>;
}

export function KeyValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="kv-label">{label}</dt>
      <dd className="kv-value break-words">{children}</dd>
    </div>
  );
}
