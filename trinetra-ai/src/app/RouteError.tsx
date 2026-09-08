import { useRouteError } from 'react-router-dom';
import { AlertOctagon } from 'lucide-react';
import { buttonClass } from '@/ui/Button';

/** Route-level error boundary — honest, calm, recoverable. */
export function RouteError() {
  const error = useRouteError() as Error;
  return (
    <div className="grid min-h-screen place-items-center bg-surface-0 p-6">
      <div className="max-w-md text-center">
        <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl border border-critical/25 bg-critical/[0.06] text-critical">
          <AlertOctagon size={20} aria-hidden />
        </span>
        <p className="mono text-xs font-semibold uppercase tracking-[0.14em] text-critical">
          Something went wrong
        </p>
        <h1 className="mt-2 text-lg font-bold text-ink">This view failed to load</h1>
        <p className="mt-2 break-words text-[13px] leading-relaxed text-ink-muted">
          {error?.message || 'An unexpected error interrupted this page.'}
        </p>
        <div className="mt-5 flex justify-center gap-2.5">
          <a href="/" className={buttonClass('primary', 'sm')}>
            Reload SENTINEL
          </a>
        </div>
      </div>
    </div>
  );
}
