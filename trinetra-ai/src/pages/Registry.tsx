import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, LayoutList, LayoutGrid } from 'lucide-react';
import { useCameras } from '@/hooks/useCameras';
import type { CameraStatus } from '@/types';
import { CameraCard } from '@/components/CameraCard';
import { CameraStatusBadge } from '@/ui/Badge';
import { Button } from '@/ui/Button';
import { Boundary } from '@/ui/Feedback';
import { useDebounced } from '@/hooks/useUi';
import { cn, relativeTime } from '@/lib/utils';
import { formatDateTime } from '@/lib/uiHelpers';

type SortKey = 'name' | 'location' | 'department' | 'status' | 'eventCount24h' | 'lastEventAt';

const STATUS_ORDER: Record<CameraStatus, number> = { ONLINE: 0, DEGRADED: 1, OFFLINE: 2 };

/**
 * Camera Registry — the authoritative installation record. A dense,
 * sortable table (with CSV export) plus a card view for browsing.
 */
export default function Registry() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const debounced = useDebounced(query, 200);
  const [status, setStatus] = useState<'ALL' | CameraStatus>('ALL');
  const [department, setDepartment] = useState('ALL');
  const [sortKey, setSortKey] = useState<SortKey>('name');
  const [asc, setAsc] = useState(true);
  const [view, setView] = useState<'table' | 'cards'>('table');

  const registryFilters = useMemo(
    () => ({
      query: debounced || undefined,
      status: status === 'ALL' ? undefined : status,
      department: department === 'ALL' ? undefined : department,
    }),
    [debounced, status, department],
  );
  const { filtered, facets, loading, error, refresh } = useCameras(registryFilters);

  const rows = useMemo(() => {
    const base = filtered;
    const sorted = [...base].sort((a, b) => {
      let r = 0;
      switch (sortKey) {
        case 'name':
          r = a.name.localeCompare(b.name);
          break;
        case 'location':
          r = a.location.localeCompare(b.location);
          break;
        case 'department':
          r = (a.department ?? '').localeCompare(b.department ?? '');
          break;
        case 'status':
          r = STATUS_ORDER[a.status] - STATUS_ORDER[b.status];
          break;
        case 'eventCount24h':
          r = (a.eventCount24h ?? 0) - (b.eventCount24h ?? 0);
          break;
        case 'lastEventAt':
          r = Date.parse(a.lastEventAt ?? '0') - Date.parse(b.lastEventAt ?? '0');
          break;
      }
      return asc ? r : -r;
    });
    return sorted;
  }, [filtered, sortKey, asc]);

  const exportCsv = () => {
    const header = [
      'id', 'name', 'location', 'department', 'zone', 'status', 'codec',
      'width', 'height', 'fps', 'streamType', 'installedAt', 'lastEventAt', 'events24h',
    ];
    const lines = rows.map((c) =>
      [c.id, c.name, c.location, c.department ?? '', c.zone ?? '', c.status, c.codec ?? '',
       c.width ?? '', c.height ?? '', c.fps ?? '', c.streamType ?? '', c.installedAt ?? '',
       c.lastEventAt ?? '', c.eventCount24h ?? 0]
        .map((v) => `"${String(v).replaceAll('"', '""')}"`)
        .join(','),
    );
    const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sentinel-camera-registry-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const sortBtn = (key: SortKey, label: string) => (
    <button
      type="button"
      onClick={() => {
        if (sortKey === key) setAsc(!asc);
        else {
          setSortKey(key);
          setAsc(true);
        }
      }}
      className={cn(
        'inline-flex items-center gap-1 uppercase transition-colors',
        sortKey === key ? 'text-ink' : 'hover:text-ink',
      )}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <span className={cn('text-[9px]', sortKey === key ? 'opacity-100' : 'opacity-0')} aria-hidden>
        {asc ? '▲' : '▼'}
      </span>
    </button>
  );

  const filterActive = debounced || status !== 'ALL' || department !== 'ALL';

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-ink">Camera Registry</h2>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-muted">
            The authoritative record of every installation — identity, placement, capture format
            and service state. Export any view as CSV for audit or planning.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-line-strong/70 p-0.5" role="group" aria-label="View mode">
            {([['table', LayoutList, 'Table view'], ['cards', LayoutGrid, 'Card view']] as const).map(([v, Icon, label]) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                aria-pressed={view === v}
                aria-label={label}
                className={cn(
                  'grid h-7.5 w-8 place-items-center rounded-md transition-all duration-150 active:scale-95',
                  view === v ? 'bg-accent-weak text-accent-strong' : 'text-ink-faint hover:text-ink',
                )}
              >
                <Icon size={14} aria-hidden />
              </button>
            ))}
          </div>
          <Button variant="secondary" onClick={exportCsv} disabled={rows.length === 0}>
            <Download size={13} aria-hidden /> Export CSV
          </Button>
        </div>
      </header>

      {/* Filters */}
      <div className="mt-5 flex flex-wrap items-center gap-2.5 rounded-xl border border-line bg-surface-1 p-3.5 shadow-xs">
        <label htmlFor="reg-search" className="sr-only">Search the registry</label>
        <input
          id="reg-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search name, location, department…"
          className="field h-9 w-64"
          type="search"
        />
        <label className="sr-only" htmlFor="reg-status">Filter by status</label>
        <select id="reg-status" className="select h-9 w-32" value={status} onChange={(e) => setStatus(e.target.value as 'ALL' | CameraStatus)}>
          <option value="ALL">All statuses</option>
          <option value="ONLINE">Online</option>
          <option value="DEGRADED">Degraded</option>
          <option value="OFFLINE">Offline</option>
        </select>
        <label className="sr-only" htmlFor="reg-dept">Filter by department</label>
        <select id="reg-dept" className="select h-9 w-40" value={department} onChange={(e) => setDepartment(e.target.value)}>
          <option value="ALL">All departments</option>
          {facets.departments.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        {filterActive && (
          <Button variant="ghost" size="xs" onClick={() => { setQuery(''); setStatus('ALL'); setDepartment('ALL'); }}>
            Reset
          </Button>
        )}
        <span className="ml-auto text-xs text-ink-faint" aria-live="polite">
          {loading ? 'Loading…' : `${rows.length} installation${rows.length === 1 ? '' : 's'}`}
        </span>
      </div>

      <Boundary
        loading={loading}
        error={error}
        onRetry={refresh}
        isEmpty={rows.length === 0}
        emptyTitle="No cameras match"
        emptyDetail="Clear a filter to see the full registry."
        className="mt-5"
      >
        {view === 'table' ? (
          <div className="overflow-x-auto rounded-xl border border-line bg-surface-1 shadow-xs">
            <table className="tbl">
              <thead>
                <tr>
                  <th>{sortBtn('name', 'Camera')}</th>
                  <th>{sortBtn('location', 'Location')}</th>
                  <th>{sortBtn('department', 'Department')}</th>
                  <th>{sortBtn('status', 'Status')}</th>
                  <th>Format</th>
                  <th>{sortBtn('eventCount24h', 'Veh · 24h')}</th>
                  <th>{sortBtn('lastEventAt', 'Last event')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="row-click" onClick={() => navigate(`/cameras/${c.id}`)}>
                    <td>
                      <span className="mono text-xs font-semibold text-ink">{c.name}</span>
                      <span className="mono ml-2 text-[10.5px] text-ink-faint">{c.id.toUpperCase()}</span>
                    </td>
                    <td className="text-ink-muted">{c.location}</td>
                    <td className="text-ink-muted">{c.department ?? '—'}</td>
                    <td>
                      <CameraStatusBadge status={c.status} />
                    </td>
                    <td className="mono text-ink-muted">
                      {c.codec ?? '—'}
                      {c.width ? ` · ${c.width}×${c.height}` : ''}
                    </td>
                    <td className="mono tabular-nums text-ink">{c.eventCount24h ?? 0}</td>
                    <td className="text-ink-muted" title={c.lastEventAt ? formatDateTime(c.lastEventAt) : undefined}>
                      {c.lastEventAt ? relativeTime(c.lastEventAt) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {rows.map((c) => (
              <CameraCard key={c.id} camera={c} />
            ))}
          </div>
        )}
      </Boundary>
    </div>
  );
}
