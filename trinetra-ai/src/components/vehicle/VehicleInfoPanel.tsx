import { ShieldAlert, ShieldCheck } from 'lucide-react';
import type { VehicleProfile } from '@/types';
import { SeverityChip } from '@/components/common/Chips';
import { KeyValue } from '@/components/common/Panel';
import { formatDateTime, prettyPlate, prettyVehicleClass } from '@/lib/utils';

/** Vehicle identity + watchlist dossier shown in the investigation workspace. */
export function VehicleInfoPanel({ profile }: { profile: VehicleProfile }) {
  const wl = profile.watchlist;

  return (
    <div className="flex flex-col gap-5 p-5">
      {wl?.active ? (
        <div className="rounded border border-critical/45 bg-critical/10 p-3.5">
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1.5 text-2xs font-bold uppercase tracking-widest text-critical">
              <ShieldAlert size={14} aria-hidden /> On the wanted list
            </p>
            <SeverityChip severity={wl.severity} />
          </div>
          <p className="mt-1 text-sm font-bold uppercase tracking-wide text-ink">{wl.category}</p>
          <p className="mt-1 text-2xs leading-relaxed text-ink-muted">{wl.reason}</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
            <KeyValue label="Case number">
              <span className="font-mono">{wl.caseRef}</span>
            </KeyValue>
            <KeyValue label="Added by">{wl.addedBy}</KeyValue>
            <KeyValue label="On list since">{formatDateTime(wl.addedAt)}</KeyValue>
            <KeyValue label="Contact">{wl.contact ?? 'Control Room — 112'}</KeyValue>
          </dl>
        </div>
      ) : (
        <div className="flex items-center gap-2.5 rounded border border-online/40 bg-online/10 p-3.5">
          <ShieldCheck size={15} className="shrink-0 text-online" aria-hidden />
          <div>
            <p className="text-2xs font-bold uppercase tracking-widest text-online">No active watchlist entry</p>
            <p className="mt-1 text-2xs text-ink-muted">
              Movement history is available for reference only — no intercept action is flagged.
            </p>
          </div>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
        <KeyValue label="Number plate">
          <span className="plate text-sm">{prettyPlate(profile.plate)}</span>
        </KeyValue>
        <KeyValue label="Type of vehicle">{prettyVehicleClass(profile.vehicleClass)}</KeyValue>
        <KeyValue label="Colour">{profile.colour ?? '—'}</KeyValue>
        <KeyValue label="State">{profile.registrationState ?? '—'}</KeyValue>
        <KeyValue label="First seen">{formatDateTime(profile.firstSeen)}</KeyValue>
        <KeyValue label="Last seen">{formatDateTime(profile.lastSeen)}</KeyValue>
        <KeyValue label="Times seen">
          <span className="font-mono tabular-nums">{profile.totalSightings}</span>
        </KeyValue>
        <KeyValue label="Owner">
          <span className="text-ink-muted">{profile.owner ?? 'Not linked to VAHAN in demo mode'}</span>
        </KeyValue>
      </dl>
    </div>
  );
}
