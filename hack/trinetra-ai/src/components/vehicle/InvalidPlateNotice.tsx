import { useNavigate } from 'react-router-dom';
import { SearchX } from 'lucide-react';

/**
 * Calm explanation for input that is not a registration number — used
 * anywhere a plate lookup fails validation, instead of a scary error.
 */
export function InvalidPlateNotice({ raw }: { raw: string }) {
  const navigate = useNavigate();
  return (
    <div className="mx-auto flex max-w-lg flex-col items-center px-6 py-10 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-surface-2 text-ink-muted" aria-hidden>
        <SearchX size={20} />
      </span>
      <h2 className="mt-3 text-base font-bold text-ink">Couldn’t look up “{raw}”</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
        That doesn’t look like a complete registration number. Indian plates look like{' '}
        <span className="font-mono font-semibold text-ink">GJ 01 AB 1234</span> — try the full
        number, or search cameras by name or place instead.
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        <button type="button" className="btn-primary" onClick={() => navigate('/vehicles')}>
          Find a vehicle
        </button>
        <button
          type="button"
          className="btn-ghost"
          onClick={() => navigate(`/cameras?search=${encodeURIComponent(raw)}`)}
        >
          Search cameras for “{raw}”
        </button>
      </div>
    </div>
  );
}
