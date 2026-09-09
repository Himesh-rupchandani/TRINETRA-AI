import { useState } from 'react';
import { Loader2, Search, X } from 'lucide-react';
import { videoAnalysisService, type PhotoEvidenceMatch, type PhotoEvidenceResult } from '@/services/videoAnalysisService';
import { formatPct, formatVideoOffset, normalisePlate, prettyPlate } from '@/lib/utils';
import { isMockMode } from '@/services/api';

/**
 * Number-plate search inside the existing Photo evidence section.
 * Returns actual frames extracted from the analysed video — never placeholders.
 */
export function PhotoEvidenceSearch({ videoId }: { videoId?: string }) {
  const [value, setValue] = useState('');
  const [result, setResult] = useState<PhotoEvidenceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const plate = normalisePlate(value);
    if (!plate || loading) return;
    if (isMockMode) {
      setError('Connect the backend to search analysed video frames.');
      setResult(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setResult(await videoAnalysisService.photoEvidence(plate, videoId));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const clear = () => {
    setValue('');
    setResult(null);
    setError(null);
  };

  return (
    <div className="border-b border-line px-4 py-3">
      <form onSubmit={run} className="flex flex-wrap gap-2">
        <input
          className="input plate flex-1 uppercase"
          placeholder="Search number plate..."
          value={value}
          onChange={(e) => setValue(e.target.value.toUpperCase())}
          spellCheck={false}
          autoComplete="off"
          aria-label="Search number plate"
        />
        <button type="submit" className="btn-primary shrink-0" disabled={loading || !value.trim()}>
          {loading ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Search size={13} aria-hidden />}
          Search
        </button>
        {(value || result) && (
          <button type="button" className="btn-ghost shrink-0" onClick={clear}>
            <X size={13} aria-hidden /> Clear
          </button>
        )}
      </form>

      {error && (
        <p className="mt-2 rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-2xs text-critical" role="alert">
          {error}
        </p>
      )}

      {result && !loading && (
        <div className="mt-3">
          {result.found ? (
            <>
              <p className="mb-2 text-2xs text-ink-muted">
                Search result: <span className="plate text-xs text-ink">{prettyPlate(result.normalized_query)}</span>
                <span className="ml-2 font-mono">
                  {result.match_count} match{result.match_count === 1 ? '' : 'es'} found
                </span>
              </p>
              <div className="grid gap-3">
                {result.matches.map((m) => (
                  <FrameCard key={`${m.evidence_ref}-${m.occurrence}`} match={m} />
                ))}
              </div>
            </>
          ) : (
            <p className="rounded-lg border border-line bg-surface-2 px-3 py-3 text-2xs text-ink-muted" role="status">
              No matching number plate found in this video.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function FrameCard({ match }: { match: PhotoEvidenceMatch }) {
  return (
    <figure className="overflow-hidden rounded border border-line bg-black">
      <img
        src={match.frame_url}
        alt={`Video frame of ${match.plate} at ${match.timestamp}`}
        className="aspect-video w-full object-cover"
        loading="lazy"
        decoding="async"
      />
      <figcaption className="space-y-0.5 border-t border-line bg-surface-1 px-3 py-2 text-2xs text-ink-muted">
        <p>
          Number Plate: <span className="plate text-xs text-ink">{prettyPlate(match.plate)}</span>
        </p>
        <p>
          Timestamp:{' '}
          <span className="font-mono text-ink">
            {match.timestamp}
            {match.video_offset_sec != null ? ` (${formatVideoOffset(match.video_offset_sec)})` : ''}
          </span>
        </p>
        {match.confidence != null && (
          <p>
            Confidence: <span className="font-mono text-ink">{formatPct(match.confidence)}</span>
          </p>
        )}
        {match.frame_number != null && (
          <p>
            Frame: <span className="font-mono text-ink">{match.frame_number}</span>
          </p>
        )}
      </figcaption>
    </figure>
  );
}
