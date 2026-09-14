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
          <h2 className="panel-title flex items-center gap-1.5">
            {Icon && <Icon size={13} className="text-ink-faint" />}
            {title}
          </h2>
          {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={cn('min-h-0 flex-1', bodyClassName)}>{children}</div>
    </section>
  );
}

export function LoadingState({ label = 'Loading', rows = 4 }: { label?: string; rows?: number }) {
  return (
    <div className="p-4" role="status" aria-live="polite" aria-busy="true">
      <div className="mb-3 flex items-center gap-2 text-2xs font-medium text-ink-faint">
        <Loader2 size={12} className="animate-spin" aria-hidden />
        {label}…
      </div>
      <div className="space-y-1.5">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton h-7" style={{ opacity: 1 - i * 0.14 }} />
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
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2.5 p-8 text-center">
      <Icon size={22} className="text-ink-faint/60" aria-hidden />
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-muted">{title}</p>
      {detail && <p className="max-w-sm text-2xs leading-relaxed text-ink-faint">{detail}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2.5 p-8 text-center" role="alert">
      <AlertOctagon size={22} className="text-critical" aria-hidden />
      <p className="text-xs font-semibold uppercase tracking-wider text-critical">Request failed</p>
      <p className="max-w-sm text-2xs text-ink-muted">{message}</p>
      {onRetry && (
        <button type="button" className="btn-ghost btn-xs mt-1" onClick={onRetry}>
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
    <div className="flex flex-col gap-0.5">
      <dt className="kv-label">{label}</dt>
      <dd className="kv-value break-words">{children}</dd>
    </div>
  );
}
