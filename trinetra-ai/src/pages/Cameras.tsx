import { useMemo, useState } from 'react';
import { useCameras } from '@/hooks/useCameras';
import { useDebounced } from '@/hooks/useUi';
import type { CameraFilters, CameraStatus } from '@/types';
import { CameraCard } from '@/components/CameraCard';
import { Boundary } from '@/ui/Feedback';
import { Tabs } from '@/ui/Tabs';
import { cn } from '@/lib/utils';

type StatusTab = 'ALL' | CameraStatus;

/**
 * Camera network — a wall of monitor tiles, filterable by status,
 * department, zone and codec. Filters are computed client-side by the
 * camera hook (facets come from the live registry).
 */
export default function Cameras() {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<StatusTab>('ALL');
  const [department, setDepartment] = useState('ALL');
  const [zone, setZone] = useState('ALL');
  const [codec, setCodec] = useState('ALL');
  const [activity, setActivity] = useState<'ANY' | 'ACTIVE' | 'QUIET'>('ANY');
  const debouncedQuery = useDebounced(query, 250);

  const filters: CameraFilters = useMemo(
    () => ({
      query: debouncedQuery || undefined,
      status: status === 'ALL' ? undefined : status,
      department: department === 'ALL' ? undefined : department,
      zone: zone === 'ALL' ? undefined : zone,
      codec: codec === 'ALL' ? undefined : codec,
      activity,
    }),
    [debouncedQuery, status, department, zone, codec, activity],
  );

  const { cameras, filtered, facets, stats, loading, error, refresh } = useCameras(filters);

  const hasFilters = status !== 'ALL' || department !== 'ALL' || zone !== 'ALL' || codec !== 'ALL' || activity !== 'ANY' || debouncedQuery !== '';

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* Filter bar */}
      <div className="flex flex-col gap-3 rounded-xl border border-line bg-surface-1 p-4 shadow-xs xl:flex-row xl:items-center">
        <label htmlFor="camera-search" className="sr-only">
          Search cameras by name, location or department
        </label>
        <input
          id="camera-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name, location, department…"
          className="field xl:max-w-xs"
          type="search"
        />
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 xl:flex xl:items-center">
          <label className="sr-only" htmlFor="f-status">Filter by status</label>
          <select id="f-status" className="select xl:w-36" value={status} onChange={(e) => setStatus(e.target.value as StatusTab)}>
            <option value="ALL">All statuses</option>
            <option value="ONLINE">Online</option>
            <option value="DEGRADED">Degraded</option>
            <option value="OFFLINE">Offline</option>
          </select>
          <label className="sr-only" htmlFor="f-dept">Filter by department</label>
          <select id="f-dept" className="select xl:w-40" value={department} onChange={(e) => setDepartment(e.target.value)}>
            <option value="ALL">All departments</option>
            {facets.departments.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <label className="sr-only" htmlFor="f-zone">Filter by zone</label>
          <select id="f-zone" className="select xl:w-36" value={zone} onChange={(e) => setZone(e.target.value)}>
            <option value="ALL">All zones</option>
            {facets.zones.map((z) => (
              <option key={z} value={z}>{z}</option>
            ))}
          </select>
          <label className="sr-only" htmlFor="f-codec">Filter by video format</label>
          <select id="f-codec" className="select xl:w-32" value={codec} onChange={(e) => setCodec(e.target.value)}>
            <option value="ALL">All formats</option>
            {facets.codecs.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-3 xl:ml-auto">
          <div className="flex items-center gap-1.5" role="group" aria-label="Filter by recent activity">
            {(['ANY', 'ACTIVE', 'QUIET'] as const).map((a) => (
              <button
                key={a}
                type="button"
                onClick={() => setActivity(a)}
                className={cn(
                  'h-8 rounded-lg border px-3 text-xs font-medium transition-all duration-150 active:scale-[0.97]',
                  activity === a
                    ? 'border-accent/30 bg-accent-weak text-accent-strong'
                    : 'border-line-strong/70 bg-surface-1 text-ink-muted hover:bg-surface-2 hover:text-ink',
                )}
                aria-pressed={activity === a}
              >
                {a === 'ANY' ? 'All' : a === 'ACTIVE' ? 'Active 24 h' : 'Quiet'}
              </button>
            ))}
          </div>
          {hasFilters && (
            <button
              type="button"
              className="text-xs font-medium text-accent hover:underline"
              onClick={() => {
                setQuery('');
                setStatus('ALL');
                setDepartment('ALL');
                setZone('ALL');
                setCodec('ALL');
                setActivity('ANY');
              }}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Status summary tabs */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={status}
          onChange={setStatus}
          items={[
            { value: 'ALL', label: 'All', count: stats.total },
            { value: 'ONLINE', label: 'Online', count: stats.online },
            { value: 'DEGRADED', label: 'Degraded', count: stats.degraded },
            { value: 'OFFLINE', label: 'Offline', count: stats.offline },
          ]}
          className="w-full overflow-x-auto sm:w-auto"
        />
        <p className="text-xs text-ink-faint" aria-live="polite">
          {loading ? 'Loading…' : `${filtered.length} of ${cameras.length} cameras`}
        </p>
      </div>

      {/* Wall */}
      <Boundary
        loading={loading}
        error={error}
        onRetry={refresh}
        isEmpty={!loading && filtered.length === 0}
        emptyTitle={hasFilters ? 'No cameras match these filters' : 'No cameras in the network'}
        emptyDetail={hasFilters ? 'Try clearing a filter or two.' : undefined}
        className="mt-4"
      >
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {filtered.map((c) => (
            <CameraCard key={c.id} camera={c} />
          ))}
        </div>
      </Boundary>
    </div>
  );
}
