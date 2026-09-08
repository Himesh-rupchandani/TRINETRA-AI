import { useMemo, useState } from 'react';
import { ShieldCheck, Search } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary } from '@/components/common/Panel';
import { Switch } from '@/components/common/Switch';
import { SeverityChip } from '@/components/common/Chips';
import { PlateLink } from '@/components/common/Links';
import { useAsync } from '@/hooks/useAsync';
import { vehicleService } from '@/services/vehicleService';
import { formatDateTime } from '@/lib/utils';

export default function Watchlist() {
  const { data, loading, error, refresh } = useAsync(() => vehicleService.watchlist(), []);
  const [query, setQuery] = useState('');
  const [onlyActive, setOnlyActive] = useState(true);

  const rows = useMemo(() => {
    const q = query.trim().toUpperCase();
    return (data ?? []).filter((w) => {
      if (onlyActive && !w.active) return false;
      if (q && !`${w.plate} ${w.category} ${w.caseRef} ${w.reason}`.toUpperCase().includes(q)) return false;
      return true;
    });
  }, [data, query, onlyActive]);

  return (
    <div className="animate-page-in flex h-full flex-col">
      <PageHeader
        title="Wanted List"
        icon={ShieldCheck}
        tone="red"
        subtitle={`${(data ?? []).filter((w) => w.active).length} vehicles are being watched. If a camera sees one, you get an alert straight away.`}
      />

      <div className="px-5 pt-5 sm:px-6 xl:px-8">
      <div className="panel flex flex-wrap items-center gap-x-8 gap-y-4 p-5">
        <div className="min-w-[240px] flex-1">
          <label className="label" htmlFor="wl-search">
            Search
          </label>
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
            <input
              id="wl-search"
              className="input pl-10"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Plate, category, case reference…"
            />
          </div>
        </div>
        <Switch
          checked={onlyActive}
          onChange={setOnlyActive}
          label="Active records only"
          className="pb-1"
        />
      </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5 sm:p-6 xl:p-8">
        <Panel>
          <AsyncBoundary
            loading={loading}
            error={error}
            onRetry={refresh}
            isEmpty={!rows.length}
            emptyTitle="No watchlist records"
            loadingLabel="Loading watchlist"
          >
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Plate</th>
                    <th scope="col">Why it is wanted</th>
                    <th scope="col">Priority</th>
                    <th scope="col">Reason</th>
                    <th scope="col">Case number</th>
                    <th scope="col">Added by</th>
                    <th scope="col">Added on</th>
                    <th scope="col">State</th>
                    <th scope="col" className="text-right">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((w) => (
                    <tr key={w.id}>
                      <td>
                        <PlateLink plate={w.plate} />
                      </td>
                      <td className="text-ink-muted">{w.category}</td>
                      <td>
                        <SeverityChip severity={w.severity} />
                      </td>
                      <td className="max-w-[320px] truncate text-ink-muted" title={w.reason}>
                        {w.reason}
                      </td>
                      <td className="font-mono text-2xs text-ink-muted">{w.caseRef}</td>
                      <td className="text-ink-muted">{w.addedBy}</td>
                      <td className="text-2xs text-ink-faint">{formatDateTime(w.addedAt)}</td>
                      <td>
                        <span
                          className={`chip ${w.active ? 'border-critical/45 bg-critical/10 text-critical' : 'border-line bg-surface-3 text-ink-faint'}`}
                        >
                          {w.active ? 'ACTIVE' : 'CLOSED'}
                        </span>
                      </td>
                      <td className="text-right">
                        <PlateLink plate={w.plate} size="xs" className="btn-ghost btn-xs" />
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
