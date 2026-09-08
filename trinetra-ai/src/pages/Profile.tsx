import { useState } from 'react';
import { BadgeCheck, Users } from 'lucide-react';
import { useOfficer } from '@/features/officer/OfficerProvider';
import { Badge } from '@/ui/Badge';
import { Card, CardBody, CardHeader, SectionLabel } from '@/ui/Card';
import { Boundary, EmptyState, KeyVal } from '@/ui/Feedback';
import { PlateLink, Stat } from '@/ui/Links';
import { cn } from '@/lib/utils';

function money(n: number) {
  return `₹${n.toLocaleString('en-IN')}`;
}

/**
 * Officer Profile — the signed-in operator's service record, plus the
 * roster. Selecting another officer switches the operating context
 * everywhere (header, ticker acknowledgements, dashboards).
 */
export default function Profile() {
  const { officers, current, loading, error, refresh, selectOfficer } = useOfficer();
  const [switching, setSwitching] = useState<string | null>(null);

  const roster = current
    ? [current, ...officers.filter((o) => o.officerId !== current.officerId)]
    : officers;

  return (
    <div className="p-4 sm:p-6">
      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        {/* Service record */}
        <div className="min-w-0">
          <Boundary loading={loading && !current} error={error} onRetry={refresh} loadingLabel="Loading service record">
            {current ? (
              <>
                <Card>
                  <CardBody className="flex flex-wrap items-center gap-5 p-6">
                    <img
                      src={current.photoUrl}
                      alt={`Portrait of ${current.name}`}
                      className="h-20 w-20 rounded-lg border border-line object-cover"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                        <h2 className="text-xl font-semibold text-ink">{current.name}</h2>
                        <Badge tone="accent">
                          <BadgeCheck size={11} aria-hidden /> On duty
                        </Badge>
                      </div>
                      <p className="mt-1 text-[13px] text-ink-muted">
                        {current.designation} · {current.department}
                      </p>
                      <p className="mono mt-0.5 text-xs text-ink-faint">
                        Badge {current.policeId} · ID {current.officerId.toUpperCase()}
                      </p>
                    </div>
                  </CardBody>
                </Card>

                <div className="mt-6 grid grid-cols-2 divide-line rounded-lg border border-line bg-surface-1 sm:grid-cols-3 sm:divide-x">
                  <Stat label="Vehicles caught" value={current.vehiclesCaught} />
                  <Stat label="Challans issued" value={current.totalChallans.toLocaleString('en-IN')} />
                  <Stat label="Challan value" value={money(current.totalChallanAmount)} />
                  <Stat label="Amount collected" value={money(current.totalAmountCollected)} />
                  <Stat
                    label="Outstanding"
                    value={money(Math.max(0, current.totalChallanAmount - current.totalAmountCollected))}
                    sub="yet to be collected"
                  />
                  <Stat label="Net revenue" value={money(current.netRevenue)} sub="fully-paid challans" />
                </div>

                <Card className="mt-6">
                  <CardHeader
                    title="Plates on this officer's books"
                    subtitle="Vehicles tied to challans issued by this officer"
                  />
                  <CardBody className="p-5">
                    {current.plates.length === 0 ? (
                      <p className="text-xs text-ink-faint">No plates associated yet.</p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {current.plates.map((p) => (
                          <PlateLink key={p} plate={p} size="sm" className="rounded-md border border-line bg-surface-2 px-2.5 py-1" />
                        ))}
                      </div>
                    )}
                  </CardBody>
                </Card>
              </>
            ) : (
              <EmptyState title="No officer signed in" detail="The service did not return an operator record." />
            )}
          </Boundary>
        </div>

        {/* Roster */}
        <aside className="min-w-0">
          <Card>
            <CardHeader
              title="Officer roster"
              subtitle="Selecting an officer switches the operating context"
              actions={<Users size={13} className="text-ink-faint" aria-hidden />}
            />
            <CardBody>
              <ul className="divide-y divide-line/70">
                {roster.map((o) => {
                  const isCurrent = current?.officerId === o.officerId;
                  return (
                    <li key={o.officerId}>
                      <button
                        type="button"
                        onClick={() => {
                          setSwitching(o.officerId);
                          selectOfficer(o.officerId);
                          setTimeout(() => setSwitching(null), 350);
                        }}
                        aria-pressed={isCurrent}
                        className={cn(
                          'flex w-full items-center gap-3.5 px-5 py-3 text-left transition-colors duration-150 hover:bg-surface-2/70 active:bg-surface-3/60',
                          isCurrent && 'bg-accent-weak/50',
                        )}
                      >
                        <img src={o.photoUrl} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover" aria-hidden />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] font-semibold text-ink">{o.name}</span>
                          <span className="block truncate text-[11px] text-ink-faint">
                            {o.designation} · {o.policeId}
                          </span>
                        </span>
                        {isCurrent ? (
                          <Badge tone="accent">Viewing</Badge>
                        ) : (
                          <span className="text-xs font-medium text-accent opacity-0 transition-opacity group-hover:opacity-100">
                            {switching === o.officerId ? 'Switching…' : 'View'}
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </CardBody>
            <CardBody className="border-t border-line px-5 py-3">
              <SectionLabel>Roster size</SectionLabel>
              <p className="mt-1 text-xs text-ink-faint">{officers.length} officers enrolled in this deployment.</p>
            </CardBody>
          </Card>

          <Card className="mt-6">
            <CardHeader title="About this deployment" subtitle="SENTINEL by TRINETRA AI" />
            <CardBody className="p-5">
              <dl className="grid gap-x-4 gap-y-4">
                <KeyVal label="Platform">SENTINEL — surveillance intelligence</KeyVal>
                <KeyVal label="Built by">TRINETRA AI</KeyVal>
                <KeyVal label="Operator role">{current?.designation ?? 'Control Center'}</KeyVal>
              </dl>
            </CardBody>
          </Card>
        </aside>
      </div>
    </div>
  );
}
