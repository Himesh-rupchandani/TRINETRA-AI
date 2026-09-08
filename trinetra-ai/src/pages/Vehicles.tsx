import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, ShieldAlert } from 'lucide-react';
import { useVehicleSearch } from '@/hooks/useVehicleSearch';
import { buttonClass } from '@/ui/Button';
import { Button } from '@/ui/Button';
import { Card, CardBody, CardHeader } from '@/ui/Card';
import { KeyVal } from '@/ui/Feedback';
import { normalisePlate } from '@/lib/utils';

/**
 * Find a Vehicle — the front door of every investigation. Recent
 * cases surface below the search so common plates are one click away.
 */
export default function Vehicles() {
  const navigate = useNavigate();
  const [q, setQ] = useState('');
  const { result, loading, error, searched, trace, reset } = useVehicleSearch();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const plate = normalisePlate(q);
    if (!plate) return;
    const found = await trace(plate);
    if (found) navigate(`/vehicles/${plate}`, { replace: false });
  };

  return (
    <div className="mx-auto max-w-3xl p-4 sm:p-6">
      <header className="text-center">
        <h2 className="text-xl font-bold text-ink">Find a Vehicle</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-muted">
          Enter a registration number to pull its full record: owner details, every camera
          sighting and the reconstructed route across the city.
        </p>
      </header>

      <form onSubmit={submit} className="mx-auto mt-6 flex max-w-xl gap-2.5" role="search">
        <label htmlFor="plate-search" className="sr-only">
          Registration number
        </label>
        <div className="relative min-w-0 flex-1">
          <Search size={15} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
          <input
            id="plate-search"
            value={q}
            onChange={(e) => setQ(e.target.value.toUpperCase())}
            placeholder="GJ01AB1234"
            className="field h-11 pl-10 font-mono text-base uppercase tracking-[0.12em]"
            autoComplete="off"
            spellCheck={false}
            autoFocus
          />
        </div>
        <Button type="submit" variant="primary" size="md" loading={loading} disabled={!normalisePlate(q)}>
          Trace
        </Button>
      </form>

      {error && (
        <p role="alert" className="mx-auto mt-4 max-w-xl rounded-lg border border-critical/25 bg-critical/[0.05] px-4 py-3 text-[13px] text-ink">
          {error}
        </p>
      )}

      {searched && result && (
        <Card className="mt-8">
          <CardHeader
            title={<span className="plate text-base">{result.plate}</span>}
            subtitle="Best match from the vehicle records"
            actions={
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  reset();
                  setQ('');
                }}
              >
                Clear
              </Button>
            }
          />
          <CardBody className="p-5">
            {result.profile?.watchlist && (
              <p className="mb-4 flex items-center gap-2 rounded-lg border border-critical/25 bg-critical/[0.05] px-3.5 py-2.5 text-[13px] font-medium text-critical">
                <ShieldAlert size={14} aria-hidden /> This vehicle is on the wanted list
                {result.profile.watchlist.caseRef && ` — ${result.profile.watchlist.caseRef}`}
              </p>
            )}
            <dl className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4">
              <KeyVal label="Make / model">
                {[result.profile?.make, result.profile?.model].filter(Boolean).join(' ') || '—'}
              </KeyVal>
              <KeyVal label="Colour">{result.profile?.colour ?? '—'}</KeyVal>
              <KeyVal label="Sightings on record">{result.profile?.totalSightings ?? result.events.length}</KeyVal>
              <KeyVal label="Owner">{result.profile?.owner ?? '—'}</KeyVal>
            </dl>
            <div className="mt-5 border-t border-line pt-4">
              <Link to={`/vehicles/${result.plate}`} className={buttonClass('primary', 'sm')}>
                Open full investigation
              </Link>
            </div>
          </CardBody>
        </Card>
      )}

      {searched && !result && !loading && !error && (
        <div className="mt-8 rounded-lg border border-line bg-surface-1 px-6 py-10 text-center">
          <p className="text-sm font-semibold text-ink">No record found</p>
          <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-ink-faint">
            {q} has never been recognised by a camera in this network. Check the number and try
            again — state code first, then district, then the letters and digits.
          </p>
        </div>
      )}

      <div className="mt-10 border-t border-line pt-5 text-center">
        <p className="text-xs text-ink-faint">
          Tip — any plate shown anywhere in SENTINEL is clickable. Try one from the{' '}
          <Link to="/events" className="font-semibold text-accent hover:underline">
            Vehicle Log
          </Link>{' '}
          or the{' '}
          <Link to="/watchlist" className="font-semibold text-accent hover:underline">
            Wanted List
          </Link>
          .
        </p>
      </div>
    </div>
  );
}
