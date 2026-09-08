import { useState } from 'react';
import { Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { videoAnalysisService } from '@/services/videoAnalysisService';
import { normalisePlate } from '@/lib/utils';
import { Button } from '@/ui/Button';

/**
 * Search a plate across processed videos; deep-links into the vehicle
 * investigation or reports "not found" from the analysis engine.
 */
export function PlateSearch({ onResult }: { onResult?: (found: boolean, plate: string) => void }) {
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const plate = normalisePlate(q);
    if (!plate) return;
    setBusy(true);
    setError(null);
    try {
      const res = await videoAnalysisService.search(plate);
      if (res.found) {
        onResult?.(true, plate);
        navigate(`/vehicles/${plate}`);
      } else {
        onResult?.(false, plate);
        setError(
          `No sighting of ${plate} in the analysed videos. Try the full vehicle log for live-camera records.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <form onSubmit={submit} className="flex gap-2.5" role="search">
        <label htmlFor="video-plate-search" className="sr-only">
          Search a plate in analysed videos
        </label>
        <div className="relative min-w-0 flex-1">
          <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
          <input
            id="video-plate-search"
            value={q}
            onChange={(e) => setQ(e.target.value.toUpperCase())}
            placeholder="e.g. GJ01AB1234"
            className="field pl-10 font-mono uppercase"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <Button type="submit" variant="primary" loading={busy} disabled={!normalisePlate(q)}>
          Search videos
        </Button>
      </form>
      {error && (
        <p role="status" className="mt-2.5 text-xs leading-relaxed text-ink-muted">
          {error}
        </p>
      )}
    </div>
  );
}
