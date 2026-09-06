import { BadgeCheck, Car, FileText, Receipt, TrendingUp, UserRound, Wallet } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel, AsyncBoundary, KeyValue } from '@/components/common/Panel';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { useAsync } from '@/hooks/useAsync';
import { officerService } from '@/services/officerService';
import { formatNumber, prettyPlate } from '@/lib/utils';

export default function Profile() {
  const profile = useAsync(() => officerService.current(), []);
  const p = profile.data;

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Officer Profile"
        icon={UserRound}
        tone="blue"
        subtitle={p ? `${p.designation} · ${p.department}` : 'Loading your profile…'}
      />

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        <AsyncBoundary
          loading={profile.loading}
          error={profile.error}
          onRetry={profile.refresh}
          loadingLabel="Loading officer profile"
        >
          {p && (
            <div className="flex flex-col gap-3 sm:gap-4">
              {/* Officer identity */}
              <section className="panel flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:gap-5">
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
          )}
        </AsyncBoundary>
      </div>
    </div>
  );
}
