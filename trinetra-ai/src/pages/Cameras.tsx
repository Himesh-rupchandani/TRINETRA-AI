import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Cctv, LayoutGrid, RefreshCcw, Search, Table2, Upload, X } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { CameraCard } from '@/components/camera/CameraCard';
import { CameraPlayer } from '@/components/camera/CameraPlayer';
import { UploadVideoModal } from '@/components/camera/UploadVideoModal';
import { Panel, AsyncBoundary, EmptyState } from '@/components/common/Panel';
import { StatusChip } from '@/components/common/Chips';
import { Modal } from '@/components/common/Modal';
import { useCameras } from '@/hooks/useCameras';
import { useDebounced, useLocalStorage } from '@/hooks/useUi';
import type { Camera, CameraFilters } from '@/types';
import { cn, formatTime, relativeTime } from '@/lib/utils';

const STATUSES = ['ALL', 'ONLINE', 'DEGRADED', 'OFFLINE'] as const;

export default function Cameras() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<CameraFilters['status']>('ALL');
  const [department, setDepartment] = useState('ALL');
  const [zone, setZone] = useState('ALL');
  const [codec, setCodec] = useState('ALL');
  const [activity, setActivity] = useState<CameraFilters['activity']>('ANY');
  const [view, setView] = useLocalStorage<'grid' | 'table'>('trinetra.cameraView', 'grid');
  const [preview, setPreview] = useState<Camera | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const debouncedQuery = useDebounced(query, 250);
  const filters = useMemo<CameraFilters>(
    () => ({ query: debouncedQuery, status, department, zone, codec, activity }),
    [debouncedQuery, status, department, zone, codec, activity],
  );

  const { filtered, facets, stats, loading, error, refresh } = useCameras(filters);
  const hasFilters =
    Boolean(query) || status !== 'ALL' || department !== 'ALL' || zone !== 'ALL' || codec !== 'ALL' || activity !== 'ANY';

  const clear = () => {
    setQuery('');
    setStatus('ALL');
    setDepartment('ALL');
    setZone('ALL');
    setCodec('ALL');
    setActivity('ANY');
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Live Cameras"
        icon={Cctv}
        tone="blue"
        subtitle={
          <>
            {stats.total} cameras · <span className="text-online">{stats.online} working</span> ·{' '}
            <span className="text-degraded">{stats.degraded} poor quality</span> ·{' '}
            <span className="text-offline">{stats.offline} not working</span>
          </>
        }
        actions={
          <>
            <div className="flex items-center gap-0.5 rounded-lg border border-line p-0.5" role="group" aria-label="View mode">
              <button
                type="button"
                onClick={() => setView('grid')}
                aria-pressed={view === 'grid'}
                className={cn(
                  'flex h-7 items-center gap-1 rounded-md px-2.5 text-2xs font-semibold transition-colors',
                  view === 'grid' ? 'bg-brand/10 text-brand' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                )}
              >
                <LayoutGrid size={12} aria-hidden /> Grid
              </button>
              <button
                type="button"
                onClick={() => setView('table')}
                aria-pressed={view === 'table'}
                className={cn(
                  'flex h-7 items-center gap-1 rounded-md px-2.5 text-2xs font-semibold transition-colors',
                  view === 'table' ? 'bg-brand/10 text-brand' : 'text-ink-muted hover:bg-surface-2 hover:text-ink',
                )}
              >
                <Table2 size={12} aria-hidden /> Table
              </button>
            </div>
            <button type="button" className="btn-ghost" onClick={refresh}>
              <RefreshCcw size={12} aria-hidden /> Refresh
            </button>
            <button type="button" className="btn-primary" onClick={() => setUploadOpen(true)}>
              <Upload size={12} aria-hidden /> Upload CCTV Video
            </button>
          </>
        }
      />

      <div className="flex flex-wrap items-end gap-3 border-b border-line bg-surface-1 px-4 py-3 sm:px-5">
        <div className="min-w-[200px] flex-1">
          <label className="label" htmlFor="cam-search">
            Search
          </label>
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
            <input
              id="cam-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by camera number or place"
              className="input pl-7"
            />
          </div>
        </div>

        <div className="w-[112px]">
          <label className="label" htmlFor="cam-status">
            Status
          </label>
          <select id="cam-status" className="select" value={status} onChange={(e) => setStatus(e.target.value as CameraFilters['status'])}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div className="w-[150px]">
          <label className="label" htmlFor="cam-dept">
            Department
          </label>
          <select id="cam-dept" className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
            <option value="ALL">ALL</option>
            {facets.departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        <div className="w-[110px]">
          <label className="label" htmlFor="cam-zone">
            Area
          </label>
          <select id="cam-zone" className="select" value={zone} onChange={(e) => setZone(e.target.value)}>
            <option value="ALL">ALL</option>
            {facets.zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </div>

        <div className="w-[96px]">
          <label className="label" htmlFor="cam-codec">
            Video format
          </label>
          <select id="cam-codec" className="select" value={codec} onChange={(e) => setCodec(e.target.value)}>
            <option value="ALL">ALL</option>
            {facets.codecs.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>

        <div className="w-[126px]">
          <label className="label" htmlFor="cam-activity">
            Seen a vehicle?
          </label>
          <select
            id="cam-activity"
            className="select"
            value={activity}
            onChange={(e) => setActivity(e.target.value as CameraFilters['activity'])}
          >
            <option value="ANY">Any</option>
            <option value="ACTIVE">Yes, today</option>
            <option value="QUIET">No, quiet</option>
          </select>
        </div>

        {hasFilters && (
          <button type="button" className="btn-ghost" onClick={clear}>
            <X size={12} aria-hidden /> Clear
          </button>
        )}
        <span className="ml-auto self-center text-2xs text-ink-faint">
          {filtered.length} of {stats.total} cameras
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={refresh}
          isEmpty={!filtered.length}
          emptyTitle="No cameras match the filters"
          emptyDetail="Adjust or clear the filters to see more of the network."
          loadingLabel="Loading camera registry"
        >
          {view === 'grid' ? (
            <div className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 2xl:grid-cols-4">
              {filtered.map((c) => (
                <CameraCard key={c.id} camera={c} onView={setPreview} />
              ))}
            </div>
          ) : (
            <Panel>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Camera</th>
                      <th scope="col">Place</th>
                      <th scope="col">Department</th>
                      <th scope="col">Zone</th>
                      <th scope="col">Status</th>
                      <th scope="col">Video format</th>
                      <th scope="col">Resolution</th>
                      <th scope="col">Events 24h</th>
                      <th scope="col">Last event</th>
                      <th scope="col" className="text-right">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((c) => (
                      <tr key={c.id}>
                        <td className="font-mono font-semibold text-ink">{c.name}</td>
                        <td className="text-ink-muted">{c.location}</td>
                        <td className="text-ink-muted">{c.department}</td>
                        <td className="text-ink-muted">{c.zone}</td>
                        <td>
                          <StatusChip status={c.status} />
                        </td>
                        <td className="font-mono text-ink-muted">{c.codec}</td>
                        <td className="font-mono text-ink-muted">
                          {c.width}×{c.height}
                        </td>
                        <td className="font-mono tabular-nums text-ink-muted">{c.eventCount24h ?? 0}</td>
                        <td className="font-mono text-ink-muted">{relativeTime(c.lastEventAt)}</td>
                        <td>
                          <div className="flex justify-end gap-1">
                            <button type="button" className="btn-ghost btn-xs" onClick={() => setPreview(c)}>
                              View
                            </button>
                            <button
                              type="button"
                              className="btn-primary btn-xs"
                              onClick={() => navigate(`/cameras/${c.id}`)}
                            >
                              Open Details
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </AsyncBoundary>
      </div>

      <UploadVideoModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={(cameraId) => {
          refresh();
          navigate(`/cameras/${cameraId.toLowerCase()}`);
        }}
      />

      <Modal
        open={Boolean(preview)}
        onClose={() => setPreview(null)}
        title={preview ? `${preview.name} — ${preview.location}` : ''}
        subtitle={preview ? `${preview.department} · ${preview.codec} · ${preview.width}×${preview.height}` : undefined}
        size="lg"
        footer={
          preview && (
            <>
              <button type="button" className="btn-ghost" onClick={() => setPreview(null)}>
                Close
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={() => {
                  navigate(`/cameras/${preview.id}`);
                  setPreview(null);
                }}
              >
                Open Full Detail
              </button>
            </>
          )
        }
      >
        {preview ? (
          <>
            <CameraPlayer camera={preview} />
            <p className="mt-2 text-2xs text-ink-faint">
              Last seen {formatTime(preview.lastSeen)} · streams are requested on demand and never auto-loaded
              for the whole grid.
            </p>
          </>
        ) : (
          <EmptyState
            title="No camera selected"
            detail="Pick a camera from the grid to preview its feed here."
          />
        )}
      </Modal>
    </div>
  );
}
