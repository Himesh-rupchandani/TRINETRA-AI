import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  Clock,
  Download,
  Eye,
  RefreshCcw,
  Repeat,
  ShieldQuestion,
  Timer,
} from 'lucide-react';
import { Panel, EmptyState } from '@/components/common/Panel';
import { PlateLink } from '@/components/common/Links';
import { cn, prettyVehicleClass } from '@/lib/utils';
import { plateUsageService, type PlateUsageReport } from '@/services/videoAnalysisService';

type SortKey = 'dwell' | 'visible' | 'first' | 'plate';

function seconds(sec?: number | null): string {
  if (sec == null) return '—';
  return `${sec.toFixed(sec < 10 ? 1 : 0)}s`;
}

/**
 * Small horizontal bar showing what share of the video this plate occupied.
 * Width comes straight from the measured dwell time — nothing is scaled to
 * make the chart look better.
 */
function PresenceBar({ pct, className }: { pct: number | null; className?: string }) {
  if (pct == null) return <span className="text-2xs text-ink-faint">—</span>;
  return (
    <div className="flex items-center gap-2" title={`${pct}% of the video`}>
      <div className={cn('h-1.5 w-16 overflow-hidden rounded-full bg-surface-3', className)}>
        <div
          className="h-full rounded-full bg-brand/70"
          style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
        />
      </div>
      <span className="font-mono text-2xs text-ink-faint">{pct.toFixed(0)}%</span>
    </div>
  );
}

function StatusChip({ status }: { status: string }) {
  if (status === 'HIGH') return null;
  return (
    <span
      className="chip border-degraded/45 bg-degraded/10 text-degraded"
      title={
        status === 'LOW_CONFIDENCE'
          ? 'OCR confidence below the trust threshold — check the evidence crop before acting on it.'
          : 'No number plate could be read for this vehicle.'
      }
    >
      <ShieldQuestion size={10} aria-hidden />
      {status === 'LOW_CONFIDENCE' ? 'Low confidence' : 'Unreadable'}
    </span>
  );
}

/**
 * Every number plate found in one video, with how long each was in shot.
 *
 * Two time columns on purpose: "in shot" is the span from first sighting to
 * last (how long it was in the area, including any time it was hidden), while
 * "on screen" counts only the frames it was actually tracked.
 */
export function PlateUsageTable({
  report,
  videoId,
  loading,
  onRefresh,
}: {
  report: PlateUsageReport | null;
  videoId?: string;
  loading?: boolean;
  onRefresh?: () => void;
}) {
  const [sort, setSort] = useState<SortKey>('dwell');
  const [showUnreadable, setShowUnreadable] = useState(false);

  const rows = useMemo(() => {
    const all = showUnreadable
      ? [...(report?.plates ?? []), ...(report?.unreadable ?? [])]
      : [...(report?.plates ?? [])];
    const cmp: Record<SortKey, (a: typeof all[number], b: typeof all[number]) => number> = {
      dwell: (a, b) => b.dwell_sec - a.dwell_sec,
      visible: (a, b) => b.visible_sec - a.visible_sec,
      first: (a, b) => a.first_seen_sec - b.first_seen_sec,
      plate: (a, b) => a.plate_label.localeCompare(b.plate_label),
    };
    return [...all].sort(cmp[sort]);
  }, [report, sort, showUnreadable]);

  const summary = report?.summary;
  const unreadableCount = report?.unreadable.length ?? 0;

  return (
    <Panel
      title="Number plates and time in shot"
      icon={Timer}
      actions={
        <>
          {unreadableCount > 0 && (
            <button
              type="button"
              className={showUnreadable ? 'btn-tint btn-xs' : 'btn-ghost btn-xs'}
              onClick={() => setShowUnreadable((v) => !v)}
              title="Vehicles that were tracked but whose plate could not be read"
            >
              +{unreadableCount} unreadable
            </button>
          )}
          <a
            className="btn-ghost btn-xs"
            href={plateUsageService.csvUrl(videoId)}
            download
            title="Download this table as CSV"
          >
            <Download size={11} aria-hidden /> CSV
          </a>
          {onRefresh && (
            <button type="button" className="btn-ghost btn-xs" onClick={onRefresh} disabled={loading}>
              <RefreshCcw size={11} aria-hidden /> Refresh
            </button>
          )}
        </>
      }
    >
      {/* --- headline numbers ------------------------------------------- */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 border-b border-line px-4 py-3 sm:grid-cols-4">
          <Stat label="Plates detected" value={summary.unique_plates} icon={Timer} />
          <Stat label="Longest in shot" value={summary.longest_dwell_label} icon={Clock} />
          <Stat
            label="Longest plate"
            value={summary.longest_plate ?? '—'}
            icon={Eye}
            mono={Boolean(summary.longest_plate)}
          />
          <Stat
            label="Watchlist hits"
            value={summary.watchlist_hits}
            icon={AlertTriangle}
            tone={summary.watchlist_hits > 0 ? 'critical' : undefined}
          />
        </div>
      )}

      {!rows.length ? (
        <EmptyState
          icon={Timer}
          title={report ? 'No number plates were read' : 'Nothing analysed yet'}
          detail={
            report
              ? 'Vehicles were processed but no number plate could be read with sufficient confidence. Nothing is invented to fill this list — turn on “unreadable” above to see the vehicles that were tracked but not identified.'
              : 'Upload a video and run the analysis to get its plate list.'
          }
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-xs">
            <thead>
              <tr className="border-b border-line text-2xs uppercase tracking-wider text-ink-faint">
                <Th sortKey="plate" active={sort} onSort={setSort}>Plate</Th>
                <th className="px-3 py-2 font-medium">Vehicle</th>
                <Th sortKey="dwell" active={sort} onSort={setSort} title="First sighting to last sighting">
                  In shot
                </Th>
                <Th sortKey="visible" active={sort} onSort={setSort} title="Frames actually tracked">
                  On screen
                </Th>
                <th className="px-3 py-2 font-medium" title="Share of the video's duration">
                  Share
                </th>
                <Th sortKey="first" active={sort} onSort={setSort}>Entry</Th>
                <th className="px-3 py-2 font-medium">Exit</th>
                <th className="px-3 py-2 font-medium" title="Separate times it entered the shot">
                  <Repeat size={11} className="inline" aria-hidden /> Entries
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line/60">
              {rows.map((row) => (
                <tr key={`${row.plate_label}-${row.track_ids.join('-')}`} className="hover:bg-surface-2">
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {row.plate ? (
                        <PlateLink plate={row.plate} />
                      ) : (
                        <span className="plate text-ink-faint">UNREADABLE</span>
                      )}
                      <StatusChip status={row.plate_status} />
                      {row.watchlist_match && (
                        <span className="chip border-critical/45 bg-critical/10 text-critical">
                          <AlertTriangle size={10} aria-hidden /> Watchlist
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-ink-muted">
                    {prettyVehicleClass(row.vehicle_class ?? '')}
                  </td>
                  <td className="px-3 py-2">
                    <span className="font-mono text-ink" title={`${row.dwell_sec.toFixed(2)} s`}>
                      {row.dwell_label}
                    </span>
                    <span className="ml-1 text-2xs text-ink-faint">{seconds(row.dwell_sec)}</span>
                  </td>
                  <td className="px-3 py-2">
                    <span className="font-mono text-ink-muted" title={`${row.visible_sec.toFixed(2)} s`}>
                      {row.visible_label}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <PresenceBar pct={row.presence_pct} />
                  </td>
                  <td className="px-3 py-2 font-mono text-ink-muted">{row.first_seen}</td>
                  <td className="px-3 py-2 font-mono text-ink-muted">{row.last_seen}</td>
                  <td className="px-3 py-2 text-ink-muted">
                    {row.appearances}
                    {row.appearances > 1 && (
                      <span
                        className="ml-1 text-2xs text-ink-faint"
                        title={row.segments
                          .map((s) => `${s.start} → ${s.end}`)
                          .join('\n')}
                      >
                        (split)
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {report?.notes?.length ? (
        <ul className="space-y-1 border-t border-line px-4 py-3">
          {report.notes.map((n) => (
            <li key={n} className="text-2xs leading-relaxed text-ink-faint">
              • {n}
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}

function Th({
  children,
  sortKey,
  active,
  onSort,
  title,
}: {
  children: React.ReactNode;
  sortKey?: SortKey;
  active?: SortKey;
  onSort?: (k: SortKey) => void;
  title?: string;
}) {
  if (!sortKey || !onSort) {
    return <th className="px-3 py-2 font-medium">{children}</th>;
  }
  return (
    <th className="px-3 py-2 font-medium" title={title}>
      <button
        type="button"
        className={cn(
          'inline-flex items-center gap-1 uppercase tracking-wider hover:text-ink',
          active === sortKey && 'text-brand',
        )}
        onClick={() => onSort(sortKey)}
      >
        {children}
        {active === sortKey && <span aria-hidden>↓</span>}
      </button>
    </th>
  );
}

function Stat({
  label,
  value,
  icon: Icon,
  tone,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  tone?: 'critical';
  mono?: boolean;
}) {
  return (
    <div className="flex items-start gap-2">
      <Icon size={13} className="mt-0.5 shrink-0 text-ink-faint" aria-hidden />
      <div className="min-w-0">
        <div className="text-2xs uppercase tracking-wider text-ink-faint">{label}</div>
        <div
          className={cn(
            'truncate text-sm font-semibold',
            mono && 'font-mono',
            tone === 'critical' ? 'text-critical' : 'text-ink',
          )}
        >
          {value}
        </div>
      </div>
    </div>
  );
}
