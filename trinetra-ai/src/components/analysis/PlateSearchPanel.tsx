import { useState } from 'react';
import { AlertTriangle, Images, Loader2, Search } from 'lucide-react';
import { Panel, EmptyState } from '@/components/common/Panel';
import { VehicleJourneyCard, CameraSequence } from '@/components/analysis/VehicleJourneyCard';
import {
  OccurrenceSkeletonGrid,
  PlateOccurrenceGrid,
} from '@/components/analysis/PlateOccurrenceGrid';
import { OccurrencePreviewModal } from '@/components/analysis/OccurrencePreviewModal';
import { videoAnalysisService, type PlateOccurrence, type PlateSearchResult } from '@/services/videoAnalysisService';
import { normalisePlate } from '@/lib/utils';

const PAGE_SIZE = 24;

/** Search one number plate across every analysed video. */
export function PlateSearchPanel({ disabled }: { disabled: boolean }) {
  const [value, setValue] = useState('');
  const [result, setResult] = useState<PlateSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PlateOccurrence | null>(null);

  const run = async (e?: React.FormEvent | null, page = 1) => {
    e?.preventDefault();
    const plate = normalisePlate(value);
    if (!plate || loading) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await videoAnalysisService.search(plate, undefined, page, PAGE_SIZE));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const gotoPage = async (page: number) => {
    const plate = normalisePlate(value);
    if (!plate || loading) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await videoAnalysisService.search(plate, undefined, page, PAGE_SIZE));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Panel title="Search number plate" icon={Search}>
      <div className="p-4">
        <form onSubmit={run} className="flex flex-wrap gap-2">
          <input
            className="input plate flex-1 uppercase"
            placeholder="GJ01AB1234"
            value={value}
            onChange={(e) => setValue(e.target.value.toUpperCase())}
            spellCheck={false}
            autoComplete="off"
            aria-label="Number plate to search"
            disabled={disabled}
          />
          <button type="submit" className="btn-primary shrink-0" disabled={disabled || loading || !value.trim()}>
            {loading ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <Search size={13} aria-hidden />}
            Search
          </button>
        </form>
        <p className="mt-2 text-2xs text-ink-faint">
          Spacing and hyphens are ignored — <span className="font-mono">GJ 01 AB 1234</span>,{' '}
          <span className="font-mono">GJ-01-AB-1234</span> and <span className="font-mono">GJ01AB1234</span>{' '}
          all match the same vehicle.
        </p>

        {error && (
          <p className="mt-3 rounded-lg border border-critical/30 bg-critical/10 px-3 py-2 text-2xs text-critical" role="alert">
            {error}
          </p>
        )}

        {loading && (
          <div className="mt-4 rounded-lg border border-line">
            <p className="flex items-center gap-2 border-b border-line px-3 py-2 text-2xs text-ink-faint" role="status">
              <Loader2 size={12} className="animate-spin" aria-hidden /> Searching vehicle records…
            </p>
            <OccurrenceSkeletonGrid />
          </div>
        )}

        {result && !loading && (
          <div className="mt-4 space-y-3">
            {/* --- Matching frames: every stored occurrence of the plate --- */}
            <div className="panel overflow-hidden">
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2.5 text-2xs font-semibold uppercase tracking-wide text-ink-muted">
                <Images size={12} className="text-ink-faint" aria-hidden />
                <span className="plate text-xs normal-case tracking-normal text-ink">{result.normalized_query}</span>
                {result.total > 0 ? (
                  <span className="chip border-brand/30 bg-brand/10 text-brand normal-case">
                    {result.total} occurrence{result.total === 1 ? '' : 's'} found
                  </span>
                ) : (
                  <span className="chip border-line bg-surface-3 text-ink-faint normal-case">no occurrences</span>
                )}
                {result.total > 0 && result.total_pages > 1 && (
                  <span className="ml-auto font-mono text-2xs font-normal normal-case text-ink-faint">
                    page {result.page}/{result.total_pages}
                  </span>
                )}
              </p>
              {result.total > 0 ? (
                <PlateOccurrenceGrid
                  occurrences={result.results}
                  total={result.total}
                  page={result.page}
                  totalPages={result.total_pages}
                  onPageChange={(p) => void gotoPage(p)}
                  onSelect={setPreview}
                />
              ) : (
                <EmptyState
                  icon={Images}
                  title="No results found"
                  detail={`No detection for "${result.normalized_query}" was found in the processed videos. Only plates the pipeline actually read appear here — nothing is generated for a plate that was never detected.`}
                />
              )}
            </div>

            {result.found && result.vehicle ? (
              <VehicleJourneyCard record={result.vehicle} defaultOpen />
            ) : null}

            {result.possible_matches.length > 0 && (
              <div className="panel border-l-4 border-l-degraded">
                <p className="flex items-center gap-1.5 border-b border-line px-4 py-2.5 text-2xs font-semibold uppercase tracking-wide text-degraded">
                  <AlertTriangle size={12} aria-hidden /> Possible matches — not confirmed
                </p>
                <ul className="divide-y divide-line/60">
                  {result.possible_matches.map((m) => (
                    <li key={m.plate} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-4 py-2.5">
                      <span className="plate text-xs text-ink">{m.plate}</span>
                      <span className="chip border-degraded/40 bg-degraded/10 text-degraded">
                        {m.differing_characters} character{m.differing_characters === 1 ? '' : 's'} differ
                      </span>
                      <CameraSequence cameras={m.cameras} />
                      <span className="ml-auto font-mono text-2xs text-ink-faint">
                        OCR {(m.best_ocr_confidence * 100).toFixed(0)}%
                      </span>
                      <span className="w-full text-2xs leading-relaxed text-ink-faint">{m.note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <OccurrencePreviewModal occurrence={preview} onClose={() => setPreview(null)} />
    </Panel>
  );
}
