import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { BadgeCheck, Car, ChevronRight, FileText, Receipt, TrendingUp, UserRound, Users, Wallet } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary, KeyValue } from '@/components/common/Panel';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { useOfficer } from '@/features/officer/OfficerProvider';
import { cn, formatNumber, prettyPlate } from '@/lib/utils';

export default function Profile() {
  const { active: p, others, loading, error, refresh, selectOfficer } = useOfficer();
  const location = useLocation();
  /* Opening Profile shows the current officer's full profile; clicking the
     profile/photo opens the Other Officers selection list. */
  const [showOthers, setShowOthers] = useState(false);

  useEffect(() => {
    setShowOthers(false);
  }, [location.key]);

  const handleSelect = (officerId: string) => {
    selectOfficer(officerId);
    setShowOthers(false);
  };

  return (
    <div className="animate-page-in flex h-full flex-col">
      <PageHeader
        title="Officer Profile"
        icon={UserRound}
        tone="blue"
        subtitle={
          p && !showOthers
            ? `${p.designation} · ${p.department}`
            : p
              ? 'Other Officers — select an officer to view their profile'
              : 'Loading your profile…'
        }
      />

      <div className="min-h-0 flex-1 overflow-auto p-5 sm:p-6 xl:p-8">
        <AsyncBoundary
          loading={loading}
          error={error}
          onRetry={refresh}
          loadingLabel="Loading officer profile"
        >
          {p && showOthers && (
            <Panel title="Other Officers" icon={Users}>
              {others.length ? (
                <ul className="divide-y divide-line">
                  {others.map((o) => (
                    <li key={o.officerId}>
                      <button
                        type="button"
                        onClick={() => handleSelect(o.officerId)}
                        className={cn(
                          'flex w-full items-center gap-3 px-4 py-3 text-left transition-colors',
                          'hover:bg-brand/5 focus-visible:bg-brand/5 focus-visible:outline-none',
                        )}
                      >
                        <img
                          src={o.photoUrl}
                          alt=""
                          className="h-11 w-11 shrink-0 rounded-full object-cover ring-1 ring-line"
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-ink">{o.name}</span>
                          <span className="block truncate text-2xs text-ink-faint">{o.designation}</span>
                        </span>
                        <ChevronRight size={15} className="shrink-0 text-ink-faint" aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-4 py-6 text-2xs text-ink-faint">No other officers available.</p>
              )}
            </Panel>
          )}

          {p && !showOthers && (
            <div className="flex flex-col gap-5">
              {/* Officer identity — click to return to the officer selection list */}
              <section className="panel overflow-hidden">
                <button
                  type="button"
                  onClick={() => setShowOthers(true)}
                  title="Switch officer"
                  className="flex w-full flex-col gap-4 p-5 text-left transition-colors hover:bg-surface-2/60 sm:flex-row sm:items-center sm:gap-5"
                >
                  <img
                    src={p.photoUrl}
                    alt={`${p.name} profile photo`}
                    className="h-20 w-20 shrink-0 rounded-full object-cover ring-2 ring-line"
                  />
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wider text-ink-faint">
                      <BadgeCheck size={13} aria-hidden />
                      {p.designation}
                    </p>
                    <h2 className="mt-1 text-xl font-bold leading-tight text-ink sm:text-2xl">{p.name}</h2>
                    <p className="mt-0.5 text-sm text-ink-muted">{p.department}</p>
                  </div>
                  <div className="flex items-center gap-4 sm:ml-auto">
                    <KeyValue label="Police ID">
                      <span className="font-mono text-sm font-semibold text-ink">{p.policeId}</span>
                    </KeyValue>
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line text-ink-muted" aria-hidden>
                      <ChevronRight size={15} />
                    </span>
                  </div>
                </button>

              </section>

              {/* Officer statistics */}
              <div className="grid grid-cols-2 gap-5 lg:grid-cols-3 xl:grid-cols-5">
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
          )}
        </AsyncBoundary>
      </div>
    </div>
  );
}
