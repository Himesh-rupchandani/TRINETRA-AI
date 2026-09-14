import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { cn, prettyPlate } from '@/lib/utils';

/** Every plate in the product is a one-click entry point into an investigation. */
export function PlateLink({
  plate,
  className,
  size = 'sm',
  pretty = false,
}: {
  plate: string;
  className?: string;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  pretty?: boolean;
}) {
  if (!plate || plate === '—') {
    return <span className="plate text-ink-faint">—</span>;
  }
  const sizes = { xs: 'text-2xs', sm: 'text-xs', md: 'text-sm', lg: 'text-base' };
  return (
    <Link
      to={`/vehicles/${plate}`}
      title={`Trace ${plate}`}
      className={cn(
        'plate group inline-flex items-center gap-1 rounded-md border border-transparent px-1 -mx-1',
        'text-ink hover:border-brand/40 hover:bg-brand/10 hover:text-brand focus-visible:text-brand',
        sizes[size],
        className,
      )}
    >
      {pretty ? prettyPlate(plate) : plate}
      <Search size={10} className="opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
    </Link>
  );
}

export function CameraLink({
  cameraId,
  label,
  className,
}: {
  cameraId: string;
  label?: string;
  className?: string;
}) {
  return (
    <Link
      to={`/cameras/${cameraId}`}
      className={cn('font-mono text-xs text-ink hover:text-brand hover:underline', className)}
      title={`Open ${label ?? cameraId}`}
    >
      {label ?? cameraId.toUpperCase()}
    </Link>
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
      className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-2.5"
      aria-label="Pagination"
    >
      <p className="text-2xs text-ink-faint">
        Showing <span className="font-semibold text-ink-muted">{from}</span>–
        <span className="font-semibold text-ink-muted">{to}</span> of{' '}
        <span className="font-semibold text-ink-muted">{total.toLocaleString('en-IN')}</span> records
      </p>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="btn-ghost btn-xs"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={12} aria-hidden /> Prev
        </button>
        <span className="px-2 font-mono text-2xs text-ink-muted">
          {page} / {pages}
        </span>
        <button
          type="button"
          className="btn-ghost btn-xs"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= pages}
          aria-label="Next page"
        >
          Next <ChevronRight size={12} aria-hidden />
        </button>
      </div>
    </nav>
  );
}

export function ConfidenceBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, value <= 1 ? value * 100 : value));
  const tone = pct >= 92 ? 'bg-online' : pct >= 80 ? 'bg-medium' : 'bg-high';
  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <div className="h-1 w-12 overflow-hidden rounded-full bg-surface-3" aria-hidden>
        <div className={cn('h-full rounded-full', tone)} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-2xs tabular-nums text-ink-muted">{pct.toFixed(1)}%</span>
    </div>
  );
}
