import { Car, IndianRupee, List, ReceiptText, UserRound } from 'lucide-react';
import { Panel, KeyValue } from '@/components/common/Panel';
import { PageHeader } from '@/components/layout/PageHeader';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { currentOfficerProfile } from '@/data/officerProfile';
import { formatNumber, prettyPlate } from '@/lib/utils';

const officer = currentOfficerProfile;

const amount = (value: number) => `₹${formatNumber(value)}`;

export default function Profile() {
  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Profile" icon={UserRound} tone="blue" subtitle="Police officer profile and statistics" />

      <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(260px,0.8fr)_minmax(0,1.8fr)]">
          <Panel title="Police Officer Profile" icon={UserRound}>
            <div className="flex flex-col items-center gap-4 p-5 text-center sm:flex-row sm:items-start sm:text-left">
              <img
                src={officer.photoUrl}
                alt={`${officer.name} profile photo`}
                className="h-24 w-24 shrink-0 rounded-full border border-line object-cover shadow-sm"
              />
              <div className="min-w-0">
                <p className="kv-label">Officer Name</p>
                <h2 className="mt-1 text-lg font-bold text-ink">{officer.name}</h2>
                <dl className="mt-3">
                  <KeyValue label="Police ID">
                    <span className="font-mono">{officer.policeId}</span>
                  </KeyValue>
                </dl>
              </div>
            </div>
          </Panel>

          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4" aria-label="Officer statistics">
            <KpiCard
              label="Total Vehicles Caught"
              value={formatNumber(officer.totalVehiclesCaught)}
              tile="blue"
              icon={Car}
            />
            <KpiCard
              label="Total Challans Given"
              value={formatNumber(officer.totalChallansGiven)}
              tile="orange"
              icon={ReceiptText}
            />
            <KpiCard
              label="Total Challan Amount"
              value={amount(officer.totalChallanAmount)}
              tile="amber"
              icon={IndianRupee}
            />
            <KpiCard
              label="Total Amount Collected"
              value={amount(officer.totalAmountCollected)}
              tile="green"
              icon={IndianRupee}
            />
            <KpiCard
              label="Net Revenue"
              value={amount(officer.netRevenue)}
              tone="brand"
              tile="purple"
              icon={IndianRupee}
            />
          </section>
        </div>

        <Panel title="Vehicle Number Plate List" icon={List} className="mt-4">
          <ul className="grid gap-2 p-4 sm:grid-cols-2 xl:grid-cols-3">
            {officer.vehicleNumberPlates.map((plate) => (
              <li key={plate} className="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
                <span className="plate text-sm text-ink">{prettyPlate(plate)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
