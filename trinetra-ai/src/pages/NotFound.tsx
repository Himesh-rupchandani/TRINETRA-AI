import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { buttonClass } from '@/ui/Button';

/** Dead-end page — quiet, helpful, on brand. */
export default function NotFound() {
  return (
    <div className="grid min-h-screen place-items-center bg-surface-0 p-6">
      <div className="max-w-sm text-center">
        <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-lg border border-line bg-surface-1 text-ink-faint">
          <Compass size={20} aria-hidden />
        </span>
        <p className="mono text-xs font-semibold uppercase tracking-[0.14em] text-ink-faint">
          404 · Not found
        </p>
        <h1 className="mt-2 text-xl font-semibold text-ink">This page is not on the map</h1>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-muted">
          The address you followed does not exist in SENTINEL. The command center is one click away.
        </p>
        <Link to="/" className={buttonClass('primary', 'sm', 'mt-5')}>
          Back to Command Center
        </Link>
        <p className="mono mt-8 text-[10.5px] tracking-wide text-ink-faint">
          SENTINEL · by TRINETRA AI
        </p>
      </div>
    </div>
  );
}
