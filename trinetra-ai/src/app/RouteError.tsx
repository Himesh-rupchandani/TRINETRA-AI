import { isRouteErrorResponse, Link, useRouteError } from 'react-router-dom';
import { AlertOctagon } from 'lucide-react';

/** Router-level error boundary so a failing screen never blanks the console. */
export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : 'Unexpected application error';

  return (
    <div className="grid min-h-screen place-items-center bg-surface-0 p-8">
      <div className="panel max-w-lg p-6 text-center">
        <AlertOctagon size={26} className="mx-auto mb-2 text-critical" aria-hidden />
        <h1 className="text-sm font-bold text-ink">Module failed to load</h1>
        <p className="mt-1.5 break-words text-2xs text-ink-muted">{message}</p>
        <div className="mt-3 flex justify-center gap-2">
          <button type="button" className="btn-ghost" onClick={() => window.location.reload()}>
            Reload
          </button>
          <Link to="/" className="btn-primary">
            Command Center
          </Link>
        </div>
      </div>
    </div>
  );
}
