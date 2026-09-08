import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useEventSearch } from '@/hooks/useEvents';

const PAGE_SIZE = 25;
import type { EventFilters, EventType, Severity, VehicleEvent } from '@/types';
import { DetectionTable } from '@/components/DetectionTable';
import { Evidence } from '@/components/Evidence';
import { Button } from '@/ui/Button';
import { Card, CardBody } from '@/ui/Card';
import { Boundary, Pagination } from '@/ui/Feedback';
import { Modal } from '@/ui/Modal';
import { cn } from '@/lib/utils';

const EVENT_TYPES: { value: EventType | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All events' },
  { value: 'VEHICLE_DETECTION', label: 'Vehicle detections' },
  { value: 'ANPR_READ', label: 'Plate reads' },
  { value: 'WATCHLIST_MATCH', label: 'Wanted matches' },
  { value: 'SPEED_VIOLATION', label: 'Speed violations' },
  { value: 'WRONG_WAY', label: 'Wrong-way driving' },
  { value: 'CAMERA_OFFLINE', label: 'Camera outages' },
];

const SEVERITIES: { value: Severity | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All priorities' },
  { value: 'CRITICAL', label: 'Critical' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
  { value: 'INFO', label: 'Info' },
];

/**
 * Vehicle Log — every event the platform has recorded, one searchable,
 * filterable, paginated table. Deep-links accept ?plate= ?cameraId=
 * ?watchlist= so other pages can land pre-filtered.
 */
export default function Events() {
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [evidence, setEvidence] = useState<VehicleEvent | null>(null);

  const [query, setQuery] = useState(params.get('plate') ?? '');
  const [eventType, setEventType] = useState<EventType | 'ALL'>(
    (params.get('eventType') as EventType) ?? 'ALL',
  );
  const [severity, setSeverity] = useState<Severity | 'ALL'>('ALL');
  const [cameraId, setCameraId] = useState(params.get('cameraId') ?? '');
  const [watchlistOnly, setWatchlistOnly] = useState(params.get('watchlist') === '1');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  const filters: EventFilters = useMemo(
    () => ({
      plate: query.trim() || undefined,
      eventType: eventType === 'ALL' ? undefined : eventType,
      severity: severity === 'ALL' ? undefined : severity,
      cameraId: cameraId.trim() || undefined,
      watchlistOnly: watchlistOnly || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
    }),
    [query, eventType, severity, cameraId, watchlistOnly, dateFrom, dateTo],
  );

  const { data, loading, error, refresh } = useEventSearch(filters, page, PAGE_SIZE);

  const applyParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const resetAll = () => {
    setQuery('');
    setEventType('ALL');
    setSeverity('ALL');
    setCameraId('');
    setWatchlistOnly(false);
    setDateFrom('');
    setDateTo('');
    setParams(new URLSearchParams(), { replace: true });
    setPage(1);
  };

  const hasFilters =
    query || eventType !== 'ALL' || severity !== 'ALL' || cameraId || watchlistOnly || dateFrom || dateTo;

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* Filter strip */}
      <Card>
        <CardBody className="p-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <div className="col-span-2">
              <label htmlFor="ev-plate" className="field-label">Registration number</label>
              <input
                id="ev-plate"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value.toUpperCase());
                  setPage(1);
                  applyParam('plate', e.target.value.toUpperCase() || null);
                }}
                placeholder="GJ01AB1234"
                className="field font-mono uppercase"
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div>
              <label htmlFor="ev-type" className="field-label">Event</label>
              <select
                id="ev-type"
                className="select"
                value={eventType}
                onChange={(e) => {
                  setEventType(e.target.value as EventType | 'ALL');
                  setPage(1);
                  applyParam('eventType', e.target.value === 'ALL' ? null : e.target.value);
                }}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="ev-sev" className="field-label">Priority</label>
              <select
                id="ev-sev"
                className="select"
                value={severity}
                onChange={(e) => {
                  setSeverity(e.target.value as Severity | 'ALL');
                  setPage(1);
                }}
              >
                {SEVERITIES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="ev-camera" className="field-label">Camera</label>
              <input
                id="ev-camera"
                value={cameraId}
                onChange={(e) => {
                  setCameraId(e.target.value);
                  setPage(1);
                  applyParam('cameraId', e.target.value || null);
                }}
                placeholder="cam04"
                className="field font-mono lowercase"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="ev-from" className="field-label">From</label>
                <input
                  id="ev-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => {
                    setDateFrom(e.target.value);
                    setPage(1);
                  }}
                  className="field px-2.5"
                />
              </div>
              <div>
                <label htmlFor="ev-to" className="field-label">To</label>
                <input
                  id="ev-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => {
                    setDateTo(e.target.value);
                    setPage(1);
                  }}
                  className="field px-2.5"
                />
              </div>
            </div>
          </div>
          <div className="mt-3.5 flex flex-wrap items-center gap-3 border-t border-line pt-3.5">
            <button
              type="button"
              role="switch"
              aria-checked={watchlistOnly}
              onClick={() => {
                setWatchlistOnly(!watchlistOnly);
                setPage(1);
                applyParam('watchlist', !watchlistOnly ? '1' : null);
              }}
              className={cn(
                'inline-flex h-8 items-center gap-2 rounded-lg border px-3 text-xs font-medium transition-all duration-150 active:scale-[0.97]',
                watchlistOnly
                  ? 'border-critical/30 bg-critical/[0.06] text-critical'
                  : 'border-line-strong/70 bg-surface-1 text-ink-muted hover:bg-surface-2 hover:text-ink',
              )}
            >
              <span
                className={cn(
                  'relative h-3.5 w-6 rounded-full border transition-colors duration-200',
                  watchlistOnly ? 'border-critical bg-critical' : 'border-line-strong bg-surface-3',
                )}
                aria-hidden
              >
                <span
                  className={cn(
                    'absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full bg-white shadow-sm transition-all duration-200',
                    watchlistOnly ? 'left-[12px]' : 'left-[1px]',
                  )}
                />
              </span>
              <ShieldAlert size={12} aria-hidden />
              Wanted matches only
            </button>
            {hasFilters && (
              <Button variant="ghost" size="xs" onClick={resetAll}>
                Reset filters
              </Button>
            )}
            <span className="ml-auto text-xs text-ink-faint" aria-live="polite">
              {loading ? 'Searching…' : data ? `${data.total.toLocaleString('en-IN')} events in range` : '—'}
            </span>
          </div>
        </CardBody>
      </Card>

      {/* Results table */}
      <Card className="mt-5">
        <CardBody>
          <Boundary
            loading={loading && !data}
            error={error}
            onRetry={refresh}
            isEmpty={!loading && (data?.items.length ?? 0) === 0}
            emptyTitle="No events match"
            emptyDetail="Widen the time range or clear a filter."
            loadingLabel="Searching the log"
          >
            <DetectionTable
              events={data?.items ?? []}
              activeEventId={null}
              onViewEvidence={(ev) => setEvidence(ev)}
            />
          </Boundary>
          {data && data.items.length > 0 && (
            <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPageChange={setPage} />
          )}
        </CardBody>
      </Card>

      {/* Evidence dialog */}
      <Modal
        open={Boolean(evidence)}
        onClose={() => setEvidence(null)}
        title="Event evidence"
        subtitle={evidence ? `${evidence.cameraName ?? evidence.cameraId.toUpperCase()} · ${evidence.location}` : undefined}
        size="lg"
        footer={
          evidence && (
            <Link
              to={`/vehicles/${evidence.plate}?evidence=${evidence.id}`}
              className="text-sm font-semibold text-accent hover:underline"
            >
              Open full investigation →
            </Link>
          )
        }
      >
        {evidence ? <Evidence ev={evidence} /> : null}
      </Modal>
    </div>
  );
}
