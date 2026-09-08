import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { EyeOff, ShieldCheck } from 'lucide-react';
import { useAsync } from '@/hooks/useAsync';
import { vehicleService } from '@/services/vehicleService';
import type { WatchlistCategory } from '@/types';
import { Badge, SeverityBadge } from '@/ui/Badge';
import { buttonClass } from '@/ui/Button';
import { Card, CardBody } from '@/ui/Card';
import { Boundary } from '@/ui/Feedback';
import { PlateLink } from '@/ui/Links';
import { Tabs } from '@/ui/Tabs';
import { useDebounced } from '@/hooks/useUi';
import { cn } from '@/lib/utils';
import { formatDateTime, relativeTime } from '@/lib/utils';

/**
 * Wanted List — the plates the network is actively looking for.
 * Table layout with category tabs; every row jumps straight into the
 * vehicle's city-wide case file.
 */
export default function Watchlist() {
  const { data, loading, error, refresh } = useAsync(() => vehicleService.watchlist(), []);
  const [tab, setTab] = useState<'ALL' | WatchlistCategory>('ALL');
  const [q, setQ] = useState('');
  const debounced = useDebounced(q, 200);

  const categories = useMemo(() => {
    const set = new Set((data ?? []).map((w) => w.category));
    return [...set];
  }, [data]);

  const filtered = useMemo(
    () =>
      (data ?? [])
        .filter((w) => w.active)
        .filter((w) => (tab === 'ALL' ? true : w.category === tab))
        .filter((w) =>
          debounced
            ? w.plate.includes(debounced.toUpperCase()) ||
              w.reason.toLowerCase().includes(debounced.toLowerCase()) ||
              w.caseRef.toLowerCase().includes(debounced.toLowerCase())
            : true,
        )
        .sort((a, b) => Date.parse(b.addedAt) - Date.parse(a.addedAt)),
    [data, tab, debounced],
  );

  const inactive = (data ?? []).filter((w) => !w.active).length;

  return (
    <div className="p-4 sm:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-ink">Wanted List</h2>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-ink-muted">
            Every plate here is cross-checked against all camera reads in realtime. A confirmed
            match raises an alert to the command center within seconds.
          </p>
        </div>
        {inactive > 0 && (
          <Badge tone="neutral" title="Records deactivated but kept for the record">
            <EyeOff size={10} aria-hidden /> {inactive} archived
          </Badge>
        )}
      </header>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: 'ALL', label: 'All categories', count: (data ?? []).filter((w) => w.active).length },
            ...categories.map((c) => ({
              value: c as WatchlistCategory,
              label: c,
              count: (data ?? []).filter((w) => w.active && w.category === c).length,
            })),
          ]}
          className="w-full overflow-x-auto sm:w-auto"
        />
        <div className="flex items-center gap-2.5">
          <label htmlFor="wl-search" className="sr-only">Search the wanted list</label>
          <input
            id="wl-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search plate, case or reason…"
            className="field h-9 w-56"
            type="search"
          />
        </div>
      </div>

      <Card className="mt-4">
        <CardBody>
          <Boundary
            loading={loading}
            error={error}
            onRetry={refresh}
            isEmpty={filtered.length === 0}
            emptyTitle="No wanted vehicles in this view"
            emptyDetail="The list is clean — nothing matches the current filter."
            loadingLabel="Loading the wanted list"
          >
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Plate</th>
                    <th>Category</th>
                    <th>Priority</th>
                    <th>Reason</th>
                    <th>Case</th>
                    <th>Added</th>
                    <th className="text-right">Case file</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((w) => (
                    <tr key={w.id}>
                      <td>
                        <span className="flex items-center gap-2">
                          <span className={cn('h-4 w-[3px] rounded-full', w.severity === 'CRITICAL' ? 'bg-critical' : w.severity === 'HIGH' ? 'bg-high' : 'bg-medium')} aria-hidden />
                          <PlateLink plate={w.plate} size="sm" pretty />
                        </span>
                      </td>
                      <td>
                        <Badge tone="neutral">{w.category}</Badge>
                      </td>
                      <td>
                        <SeverityBadge severity={w.severity} />
                      </td>
                      <td className="max-w-[280px]">
                        <span className="block truncate whitespace-normal text-ink-muted" title={w.reason}>
                          {w.reason}
                        </span>
                      </td>
                      <td className="mono text-ink-muted">{w.caseRef}</td>
                      <td className="text-ink-muted">
                        <span title={formatDateTime(w.addedAt)}>{relativeTime(w.addedAt)}</span>
                        <span className="ml-1.5 text-[11px] text-ink-faint">by {w.addedBy}</span>
                      </td>
                      <td className="text-right">
                        <Link to={`/vehicles/${w.plate}`} className={buttonClass('ghost', 'xs')}>
                          <ShieldCheck size={11} aria-hidden /> Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Boundary>
        </CardBody>
      </Card>
    </div>
  );
}
