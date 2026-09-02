import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowDownUp, Download, ScrollText, Search } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary } from '@/components/common/Panel';
import { StatusChip } from '@/components/common/Chips';
import { useCameras } from '@/hooks/useCameras';
import { useDebounced } from '@/hooks/useUi';
import type { Camera, CameraFilters } from '@/types';
import { cn, formatDateTime, relativeTime } from '@/lib/utils';

type SortKey = 'name' | 'location' | 'department' | 'status' | 'eventCount24h' | 'lastEventAt';
type SortState = { key: SortKey; dir: 'asc' | 'desc' };

/** Sortable column header (module scope so it is never re-created per render). */
function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (k: SortKey) => void;
}) {
  const activeCol = sort.key === sortKey;
  return (
    <th scope="col" aria-sort={activeCol ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn('inline-flex items-center gap-1 hover:text-ink', activeCol && 'text-brand')}
      >
        {label}
        <ArrowDownUp size={9} aria-hidden />
      </button>
    </th>
  );
}

/**
 * CAMERA REGISTRY — Model 1 surfaced directly in the product:
 * master records, GIS coordinates, codecs, resolution and heartbeat.
 */
export default function Registry() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<CameraFilters['status']>('ALL');
  const [department, setDepartment] = useState('ALL');
  const [sort, setSort] = useState<SortState>({ key: 'name', dir: 'asc' });

  const debounced = useDebounced(query, 250);
  const { filtered, facets, stats, loading, error, refresh } = useCameras({
    query: debounced,
    status,
    department,
  });

  const rows = useMemo(() => {
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sort.key as keyof Camera];
      const bv = b[sort.key as keyof Camera];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [filtered, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }));

  const exportCsv = () => {
    const header = [
      'camera_id',
      'name',
      'department',
      'location',
      'latitude',
      'longitude',
      'status',
      'codec',
      'resolution',
      'last_seen',
    ];
    const lines = rows.map((c) =>
      [
        c.id,
        c.name,
        c.department ?? '',
        `"${c.location}"`,
        c.latitude,
        c.longitude,
        c.status,
        c.codec ?? '',
        `${c.width}x${c.height}`,
        c.lastSeen ?? '',
      ].join(','),
    );
    const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'trinetra-camera-registry.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Camera List"
        icon={ScrollText}
        tone="blue"
        subtitle={`Full details for all ${stats.total} cameras. Sort any column, or export the list.`}
        actions={
          <button type="button" className="btn-ghost" onClick={exportCsv}>
            <Download size={12} aria-hidden /> Export CSV
          </button>
        }
      />

      <div className="flex flex-wrap items-end gap-3 border-b border-line bg-surface-1 px-4 py-3 sm:px-5">
        <div className="min-w-[220px] flex-1">
          <label className="label" htmlFor="reg-search">
            Search cameras
          </label>
          <div className="relative">
            <Search size={13} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
            <input
              id="reg-search"
              className="input pl-7"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by camera number, place or department"
            />
          </div>
        </div>
        <div className="w-[120px]">
          <label className="label" htmlFor="reg-status">
            Status
          </label>
          <select
            id="reg-status"
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value as CameraFilters['status'])}
          >
            {['ALL', 'ONLINE', 'DEGRADED', 'OFFLINE'].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="w-[160px]">
          <label className="label" htmlFor="reg-dept">
            Department
          </label>
          <select id="reg-dept" className="select" value={department} onChange={(e) => setDepartment(e.target.value)}>
            <option value="ALL">ALL</option>
            {facets.departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="ml-auto flex items-center gap-2 self-center text-2xs">
          <span className="chip border-online/45 bg-online/10 text-online">{stats.online} working</span>
          <span className="chip border-degraded/45 bg-degraded/10 text-degraded">{stats.degraded} poor quality</span>
          <span className="chip border-offline/45 bg-offline/10 text-offline">{stats.offline} not working</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        <Panel>
          <AsyncBoundary
            loading={loading}
            error={error}
            onRetry={refresh}
            isEmpty={!rows.length}
            emptyTitle="No registry records"
            loadingLabel="Loading registry"
          >
            <div className="overflow-x-auto">
              <table className="data-table">
                <caption className="sr-only">Camera registry master records</caption>
                <thead>
                  <tr>
                    <SortHeader label="Camera ID" sortKey="name" sort={sort} onSort={toggleSort} />
                    <th scope="col">Name</th>
                    <SortHeader label="Department" sortKey="department" sort={sort} onSort={toggleSort} />
                    <SortHeader label="Place" sortKey="location" sort={sort} onSort={toggleSort} />
                    <th scope="col">Latitude</th>
                    <th scope="col">Longitude</th>
                    <SortHeader label="Status" sortKey="status" sort={sort} onSort={toggleSort} />
                    <th scope="col">Video format</th>
                    <th scope="col">Picture size</th>
                    <SortHeader label="Vehicles today" sortKey="eventCount24h" sort={sort} onSort={toggleSort} />
                    <SortHeader label="Last vehicle" sortKey="lastEventAt" sort={sort} onSort={toggleSort} />
                    <th scope="col" className="text-right">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((c) => (
                    <tr key={c.id}>
                      <td className="font-mono text-ink-faint">{c.id}</td>
                      <td className="font-mono font-semibold text-ink">{c.name}</td>
                      <td className="text-ink-muted">{c.department}</td>
                      <td className="text-ink-muted">{c.location}</td>
                      <td className="font-mono tabular-nums text-ink-muted">{c.latitude.toFixed(5)}</td>
                      <td className="font-mono tabular-nums text-ink-muted">{c.longitude.toFixed(5)}</td>
                      <td>
                        <StatusChip status={c.status} />
                      </td>
                      <td className="font-mono text-ink-muted">{c.codec}</td>
                      <td className="font-mono text-ink-muted">
                        {c.width}×{c.height}
                      </td>
                      <td className="font-mono tabular-nums text-ink-muted">{c.eventCount24h ?? 0}</td>
                      <td className="text-ink-muted" title={formatDateTime(c.lastSeen)}>
                        {relativeTime(c.lastSeen)}
                      </td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="btn-ghost btn-xs"
                          onClick={() => navigate(`/cameras/${c.id}`)}
                        >
                          Open
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </AsyncBoundary>
        </Panel>
      </div>
    </div>
  );
}
