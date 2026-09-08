import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LayoutGrid, RefreshCcw, Search, SlidersHorizontal, Table2, Upload, X } from 'lucide-react';
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
  const [advanced, setAdvanced] = useState(false);
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
    <div className="animate-page-in flex h-full flex-col">
      <div className="px-5 pt-6 sm:px-6 xl:px-8">
        <PageHeader
          title="Live Cameras"
          subtitle={
            <>
              {stats.total} cameras · <span className="text-online">{stats.online} working</span> ·{' '}
              <span className="text-degraded">{stats.degraded} poor quality</span> ·{' '}
              <span className="text-offline">{stats.offline} not working</span>
            </>
          }
          actions={
            <>
              <div className="flex items-center gap-1 rounded-lg border border-line p-1" role="group" aria-label="View mode">
                <button
                  type="button"
                  onClick={() => setView('grid')}
                  aria-pressed={view === 'grid'}
                  className={cn(
                    'flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors',
                    view === 'grid' ? 'bg-surface-3 text-ink' : 'text-ink-muted hover:text-ink',
                  )}
                >
                  <LayoutGrid size={13} aria-hidden /> Grid
                </button>
                <button
                  type="button"
                  onClick={() => setView('table')}
                  aria-pressed={view === 'table'}
                  className={cn(
                    'flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors',
                    view === 'table' ? 'bg-surface-3 text-ink' : 'text-ink-muted hover:text-ink',
                  )}
                >
                  <Table2 size={13} aria-hidden /> Table
                </button>
              </div>
              <button type="button" className="btn-ghost" onClick={refresh}>
                <RefreshCcw size={13} aria-hidden /> Refresh
              </button>
              <button type="button" className="btn-primary" onClick={() => setUploadOpen(true)}>
                <Upload size={13} aria-hidden /> Upload CCTV Video
              </button>
            </>
          }
        />
      </div>

      {/* Search always visible; secondary filters expand on demand */}
      <div className="px-5 pb-5 pt-4 sm:px-6 xl:px-8">
        <div className="panel p-5">
          <div className="flex flex-wrap items-end gap-x-5 gap-y-4">
            <div className="min-w-[240px] flex-1">
              <label className="label" htmlFor="cam-search">
                Search
              </label>
              <div className="relative">
                <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
                <input
                  id="cam-search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by camera number or place"
                  className="input pl-10"
                />
              </div>
            </div>

            <div className="w-[150px]">
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

            <button
              type="button"
              className="btn-ghost"
              onClick={() => setAdvanced((v) => !v)}
              aria-expanded={advanced}
            >
              <SlidersHorizontal size={13} aria-hidden />
              {advanced ? 'Hide filters' : 'More filters'}
            </button>

            {hasFilters && (
              <button type="button" className="btn-ghost" onClick={clear}>
                <X size={13} aria-hidden /> Clear all
              </button>
            )}

            <span className="ml-auto self-center text-2xs text-ink-faint">
              Showing {filtered.length} of {stats.total}
            </span>
          </div>

          {advanced && (
            <div className="mt-5 grid gap-x-5 gap-y-4 border-t border-line pt-5 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="label" htmlFor="cam-dept">
                  Department
                </label>
                <select id="cam-dept" className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
                  <option value="ALL">All departments</option>
                  {facets.departments.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label" htmlFor="cam-zone">
                  Area
                </label>
                <select id="cam-zone" className="select" value={zone} onChange={(e) => setZone(e.target.value)}>
                  <option value="ALL">All areas</option>
                  {facets.zones.map((z) => (
                    <option key={z} value={z}>
                      {z}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label" htmlFor="cam-codec">
                  Video format
                </label>
                <select id="cam-codec" className="select" value={codec} onChange={(e) => setCodec(e.target.value)}>
                  <option value="ALL">All formats</option>
                  {facets.codecs.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>

              <div>
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
            </div>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-5 pb-6 sm:px-6 xl:px-8">
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
            <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
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
          <EmptyState title="No camera selected" />
        )}
      </Modal>
    </div>
  );
}
