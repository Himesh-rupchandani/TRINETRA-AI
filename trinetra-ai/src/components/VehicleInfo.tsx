import type { VehicleProfile } from '@/types';
import { KeyVal } from '@/ui/Feedback';
import { Badge } from '@/ui/Badge';
import { AlertTriangle } from 'lucide-react';
import { formatDateTime } from '@/lib/uiHelpers';

/** Wanted-list banner shown above the vehicle dossier. */
export function WantedBanner({ profile }: { profile: VehicleProfile }) {
  const w = profile.watchlist;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-critical/30 bg-critical/[0.05] px-5 py-3.5">
      <AlertTriangle size={16} className="shrink-0 text-critical" aria-hidden />
      <p className="text-[13px] font-semibold text-critical">This vehicle is on the wanted list</p>
      {w?.caseRef && (
        <span className="mono rounded-md border border-critical/30 bg-white/70 px-2 py-0.5 text-[11px] font-semibold text-critical">
          {w.caseRef}
        </span>
      )}
      {w?.reason && <p className="text-xs text-ink-muted">{w.reason}</p>}
      <Badge tone="danger" className="ml-auto">
        Verify before approach
      </Badge>
    </div>
  );
}

/** Structured vehicle dossier — plain facts in a definition grid. */
export function VehicleInfoPanel({ profile }: { profile: VehicleProfile }) {
  return (
    <dl className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-3">
      <KeyVal label="Registration">
        <span className="plate rounded border border-line bg-surface-2 px-2 py-0.5 tracking-[0.12em]">
          {profile.plate}
        </span>
      </KeyVal>
      <KeyVal label="Status">
        {profile.watchlist ? <Badge tone="danger">Wanted</Badge> : <Badge tone="success">No flags</Badge>}
      </KeyVal>
      <KeyVal label="Vehicle class">{profile.vehicleClass ?? '—'}</KeyVal>
      <KeyVal label="Make / model">
        {[profile.make, profile.model].filter(Boolean).join(' ') || '—'}
      </KeyVal>
      <KeyVal label="Colour">{profile.colour ?? '—'}</KeyVal>
      <KeyVal label="Owner">{profile.owner ?? '—'}</KeyVal>
      <KeyVal label="Registration state">{profile.registrationState ?? '—'}</KeyVal>
      <KeyVal label="Total sightings">{profile.totalSightings.toLocaleString('en-IN')}</KeyVal>
      <KeyVal label="Cameras recorded on">{profile.camerasTouched ?? '—'}</KeyVal>
      <KeyVal label="First seen">
        {profile.firstSeen ? formatDateTime(profile.firstSeen) : '—'}
      </KeyVal>
      <KeyVal label="Last seen">
        {profile.lastSeen ? formatDateTime(profile.lastSeen) : '—'}
      </KeyVal>
      {profile.watchlist && (
        <KeyVal label="Wanted since">
          {profile.watchlist.addedAt ? formatDateTime(profile.watchlist.addedAt) : '—'}
        </KeyVal>
      )}
    </dl>
  );
}
