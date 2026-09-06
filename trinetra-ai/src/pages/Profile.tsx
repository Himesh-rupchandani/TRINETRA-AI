import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { BadgeCheck, Car, FileText, Receipt, TrendingUp, UserRound, Wallet } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary, KeyValue } from '@/components/common/Panel';
import { OfficerAvatar } from '@/components/common/OfficerAvatar';
import { OfficerSwitcher } from '@/components/common/OfficerSwitcher';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { refreshOfficers, setCurrentOfficer, useOfficerState } from '@/hooks/useCurrentOfficer';
import { formatNumber, prettyPlate } from '@/lib/utils';

/**
 * Officer Profile.
 *
 * Opening this page from the sidebar shows the officer selection list first —
 * only photo, name and rank. Picking an officer replaces the list with that
 * officer's complete profile. Arriving here from the profile-area picker
 * carries the chosen officer in the navigation state and skips straight to
 * their details.
 */
export default function Profile() {
  const { current, roster, loading, error } = useOfficerState();
  const location = useLocation();
  const requestedId = (location.state as { officerId?: string } | null)?.officerId ?? null;

  // Re-entering the page (e.g. the sidebar "Profile" item) resets to the list.
  // Derived during render — React's documented "reset state on prop change"
  // pattern, which avoids a cascading effect render.
  const [visit, setVisit] = useState({ key: location.key, selectedId: requestedId });
  if (visit.key !== location.key) setVisit({ key: location.key, selectedId: requestedId });
  const selectedId = visit.selectedId;
  const selectOfficer = (id: string) => setVisit({ key: location.key, selectedId: id });

  const byId = (id: string | null) =>
    id ? (roster.find((o) => o.officerId === id) ?? (current?.officerId === id ? current : null)) : null;

  const p = byId(selectedId);
  const others = roster.filter((o) => o.officerId !== current?.officerId);

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Officer Profile"
        icon={UserRound}
        tone="blue"
        subtitle={p ? `${p.designation} · ${p.department}` : 'Select an officer'}
      />

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={refreshOfficers}
          loadingLabel="Loading officer profile"
        >
          {p ? (
            <div className="flex flex-col gap-3 sm:gap-4">
              {/* Officer identity */}
              <section className="panel flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:gap-5">
                <OfficerSwitcher
                  placement="bottom-start"
                  className="shrink-0"
                  buttonClassName="block rounded-full outline-none ring-brand/40 transition-shadow hover:ring-2 focus-visible:ring-2"
                >
                  <OfficerAvatar officer={p} size={80} className="ring-2 ring-line" />
                </OfficerSwitcher>
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wider text-ink-faint">
                    <BadgeCheck size={13} aria-hidden />
                    {p.designation}
                  </p>
                  <h2 className="mt-1 text-xl font-bold leading-tight text-ink sm:text-2xl">{p.name}</h2>
                  <p className="mt-0.5 text-sm text-ink-muted">{p.department}</p>
                </div>
                <div className="sm:ml-auto">
                  <KeyValue label="Police ID">
                    <span className="font-mono text-sm font-semibold text-ink">{p.policeId}</span>
                  </KeyValue>
                </div>
              </section>

              {/* Officer statistics */}
              <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-5">
                <KpiCard label="Total Vehicles Caught" value={formatNumber(p.vehiclesCaught)} tile="blue" icon={Car} />
                <KpiCard label="Total Challans Given" value={formatNumber(p.totalChallans)} tile="orange" icon={FileText} />
                <KpiCard label="Total Challan Amount" value={<>₹{formatNumber(p.totalChallanAmount)}</>} tile="amber" icon={Receipt} />
                <KpiCard label="Total Amount Collected" value={<>₹{formatNumber(p.totalAmountCollected)}</>} tile="green" icon={Wallet} />
                <KpiCard label="Net Revenue" value={<>₹{formatNumber(p.netRevenue)}</>} tile="purple" icon={TrendingUp} />
              </div>

              {/* Vehicle number plate list */}
              <Panel title="Vehicle Number Plate List" icon={Car}>
                {p.plates.length ? (
                  <ul className="flex flex-wrap gap-2 p-4">
                    {p.plates.map((plate) => (
                      <li key={plate}>
                        <span className="chip border-brand/25 bg-brand/10 font-mono font-bold tracking-wider text-brand">
                          {prettyPlate(plate)}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="px-4 py-6 text-2xs text-ink-faint">
                    No vehicle number plates recorded for this officer.
                  </p>
                )}
              </Panel>
            </div>
          ) : (
            /* Officer selection list — photo, name and rank only. */
            <Panel title="Other Officers" icon={UserRound}>
              {others.length ? (
                <ul className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
                  {others.map((officer) => (
                    <li key={officer.officerId}>
                      <button
                        type="button"
                        onClick={() => {
                          setCurrentOfficer(officer);
                          selectOfficer(officer.officerId);
                        }}
                        className="flex w-full items-center gap-3 rounded-xl border border-line bg-surface-1 p-3 text-left transition-colors hover:border-brand/25 hover:bg-surface-2"
                      >
                        <OfficerAvatar officer={officer} size={44} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold leading-tight text-ink">
                            {officer.name}
                          </span>
                          <span className="block truncate text-2xs text-ink-faint">{officer.position}</span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-4 py-6 text-2xs text-ink-faint">No other officers available.</p>
              )}
            </Panel>
          )}
        </AsyncBoundary>
      </div>
    </div>
  );
}
