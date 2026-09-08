import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FileImage, ListTree, RefreshCcw, X } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary } from '@/components/common/Panel';
import { Pagination, PlateLink, ConfidenceBar, CameraLink } from '@/components/common/Links';
import { SeverityChip } from '@/components/common/Chips';
import { Modal } from '@/components/common/Modal';
import { Switch } from '@/components/common/Switch';
import { EvidencePanel } from '@/components/vehicle/EvidencePanel';
import { useEventSearch } from '@/hooks/useEvents';
import { useCameras } from '@/hooks/useCameras';
import { useDebounced } from '@/hooks/useUi';
import type { EventFilters, EventType, Severity, VehicleEvent } from '@/types';
import { formatDate, formatTime, prettyEventType, prettyVehicleClass } from '@/lib/utils';

const EVENT_TYPES: (EventType | 'ALL')[] = [
  'ALL',
  'VEHICLE_DETECTION',
  'ANPR_READ',
  'WATCHLIST_MATCH',
  'SPEED_VIOLATION',
  'WRONG_WAY',
  'CAMERA_OFFLINE',
];
const SEVERITIES: (Severity | 'ALL')[] = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const PAGE_SIZE = 25;

export default function Events() {
  const [params, setParams] = useSearchParams();
  const { cameras } = useCameras();

  const [plate, setPlate] = useState(params.get('plate') ?? '');
  const [cameraId, setCameraId] = useState(params.get('cameraId') ?? 'ALL');
  const [eventType, setEventType] = useState<EventType | 'ALL'>('ALL');
  const [severity, setSeverity] = useState<Severity | 'ALL'>('ALL');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [timeFrom, setTimeFrom] = useState('');
  const [timeTo, setTimeTo] = useState('');
  const [watchlistOnly, setWatchlistOnly] = useState(params.get('watchlist') === 'true');
  const [page, setPage] = useState(1);
  const [evidence, setEvidence] = useState<VehicleEvent | null>(null);

  const debouncedPlate = useDebounced(plate, 300);

  const filters = useMemo<EventFilters>(
    () => ({
      plate: debouncedPlate || undefined,
      cameraId,
      eventType,
      severity,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      timeFrom: timeFrom || undefined,
      timeTo: timeTo || undefined,
      watchlistOnly,
    }),
    [debouncedPlate, cameraId, eventType, severity, dateFrom, dateTo, timeFrom, timeTo, watchlistOnly],
  );

  // Reset paging when the query changes (adjust-state-during-render pattern —
  // avoids the extra effect round-trip and a flash of the old page).
  const filterKey = JSON.stringify(filters);
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    setPage(1);
  }

  const { data, loading, error, refresh } = useEventSearch(filters, page, PAGE_SIZE);
  const items = data?.items ?? [];

  const clear = () => {
    setPlate('');
    setCameraId('ALL');
    setEventType('ALL');
    setSeverity('ALL');
    setDateFrom('');
    setDateTo('');
    setTimeFrom('');
    setTimeTo('');
    setWatchlistOnly(false);
    setParams({});
  };

  const active =
    plate || cameraId !== 'ALL' || eventType !== 'ALL' || severity !== 'ALL' || dateFrom || dateTo || timeFrom || timeTo || watchlistOnly;

  return (
    <div className="animate-page-in flex h-full flex-col">
      <PageHeader
        title="Vehicle Log"
        icon={ListTree}
        tone="green"
        subtitle={`Every vehicle the cameras have seen. ${(data?.total ?? 0).toLocaleString('en-IN')} match your filters.`}
        actions={
          <button type="button" className="btn-ghost" onClick={refresh}>
            <RefreshCcw size={12} aria-hidden /> Refresh
          </button>
        }
      />

      <div className="border-b border-line px-5 py-5 sm:px-6 xl:px-8">
        <div className="grid grid-cols-2 gap-x-5 gap-y-4 lg:grid-cols-4">
        <div className="col-span-2 sm:col-span-1">
          <label className="label" htmlFor="f-plate">
            Number plate
          </label>
          <input
            id="f-plate"
            className="input plate uppercase"
            value={plate}
            onChange={(e) => setPlate(e.target.value.toUpperCase())}
            placeholder="GJ01AB1234"
          />
        </div>
        <div>
          <label className="label" htmlFor="f-camera">
            Camera
          </label>
          <select id="f-camera" className="select" value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
            <option value="ALL">ALL</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-type">
            What happened
          </label>
          <select
            id="f-type"
            className="select"
            value={eventType}
            onChange={(e) => setEventType(e.target.value as EventType | 'ALL')}
          >
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {prettyEventType(t)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-sev">
            Priority
          </label>
          <select
            id="f-sev"
            className="select"
            value={severity}
            onChange={(e) => setSeverity(e.target.value as Severity | 'ALL')}
          >
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-from">
            From date
          </label>
          <input id="f-from" type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="f-to">
            To date
          </label>
          <input id="f-to" type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="f-tfrom">
            From time
          </label>
          <input id="f-tfrom" type="time" className="input" value={timeFrom} onChange={(e) => setTimeFrom(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="f-tto">
            To time
          </label>
          <input id="f-tto" type="time" className="input" value={timeTo} onChange={(e) => setTimeTo(e.target.value)} />
        </div>

        <div className="col-span-2 flex items-center gap-6 sm:col-span-4">
          <Switch
            checked={watchlistOnly}
            onChange={setWatchlistOnly}
            label="Only wanted vehicles"
            className="min-w-[240px]"
          />
          {active && (
            <button type="button" className="btn-ghost" onClick={clear}>
              <X size={13} aria-hidden /> Clear filters
            </button>
          )}
        </div>
      </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5 sm:p-6 xl:p-8">
        <Panel bodyClassName="flex flex-col">
          <AsyncBoundary
            loading={loading}
            error={error}
            onRetry={refresh}
            isEmpty={!items.length}
            emptyTitle="No events found"
            emptyDetail="Try widening the date range or clearing filters."
            loadingLabel="Querying event index"
          >
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Date</th>
                    <th scope="col">Time</th>
                    <th scope="col">Camera</th>
                    <th scope="col">Place</th>
                    <th scope="col">Plate</th>
                    <th scope="col">Vehicle type</th>
                    <th scope="col">Plate match</th>
                    <th scope="col">What happened</th>
                    <th scope="col">Priority</th>
                    <th scope="col" className="text-right">
                      Photo
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((e) => (
                    <tr key={e.id}>
                      <td className="font-mono text-2xs text-ink-faint">{formatDate(e.timestamp)}</td>
                      <td className="font-mono tabular-nums text-ink">{formatTime(e.timestamp)}</td>
                      <td>
                        <CameraLink cameraId={e.cameraId} label={e.cameraName} />
                      </td>
                      <td className="max-w-[190px] truncate text-ink-muted">{e.location}</td>
                      <td>
                        <PlateLink plate={e.plate} size="xs" />
                      </td>
                      <td className="text-ink-muted">{prettyVehicleClass(e.vehicleClass)}</td>
                      <td>{e.plateConfidence ? <ConfidenceBar value={e.plateConfidence} /> : '—'}</td>
                      <td className="text-2xs text-ink-muted">{prettyEventType(e.eventType)}</td>
                      <td>
                        <SeverityChip severity={e.severity ?? 'INFO'} />
                      </td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="btn-ghost btn-xs"
                          onClick={() => setEvidence(e)}
                          disabled={!e.evidence}
                        >
                          <FileImage size={10} aria-hidden /> View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              pageSize={PAGE_SIZE}
              total={data?.total ?? 0}
              onPageChange={(p) => setPage(Math.max(1, p))}
            />
          </AsyncBoundary>
        </Panel>
      </div>

      <Modal
        open={Boolean(evidence)}
        onClose={() => setEvidence(null)}
        title={evidence ? `Evidence — ${evidence.plate}` : ''}
        subtitle={evidence ? `${evidence.cameraName} · ${evidence.location}` : undefined}
      >
        <EvidencePanel event={evidence} />
      </Modal>
    </div>
  );
}
