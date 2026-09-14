import { useAsync } from '@/hooks/useAsync';
import { apiUrl } from '@/services/api';
import { Gauge, MapPin, Clock, Shield, FileCheck } from 'lucide-react';

interface SpeedSegment {
  from_camera: string;
  to_camera: string;
  from_name: string;
  to_name: string;
  distance_km: number;
  time_delta_human: string;
  avg_speed_kmh: number;
  is_violation: boolean;
  severity: string;
  max_allowed_kmh: number;
  overspeed_by_kmh: number;
  evidence_hash: string;
  bsa_compliant: boolean;
}

interface SpeedAnalysis {
  plate: string;
  total_distance_km: number;
  total_duration_human: string;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  violation_count: number;
  critical_violations: number;
  is_overspeeding: boolean;
  segments: SpeedSegment[];
  bsa_compliant: boolean;
  court_admissible: boolean;
  speed_limit_kmh: number;
}

export function SpeedViolationPanel({ plate }: { plate: string }) {
  const analysis = useAsync(async () => {
    const res = await fetch(apiUrl(`/vehicles/${plate}/speed-analysis`));
    if (!res.ok) throw new Error(`Speed analysis responded ${res.status}`);
    return (await res.json()) as SpeedAnalysis;
  }, [plate]);

  if (analysis.loading) return <div className="panel p-4"><div className="skeleton h-32 w-full" /></div>;

  if (analysis.error || !analysis.data) {
    return (
      <div className="panel p-4">
        <div className="flex items-center gap-2 text-ink-faint">
          <Gauge size={16} />
          <p className="text-xs">Speed analysis requires 2+ GPS-tagged sightings — try demo plate GJ01AB1234{analysis.error ? ` (backend error: ${analysis.error})` : ''}</p>
        </div>
      </div>
    );
  }

  const data = analysis.data;
  const segments = data.segments ?? [];
  const violationCount = data.violation_count ?? 0;

  return (
    <div className="panel overflow-hidden">
      <div className="panel-header bg-gradient-to-r from-blue-50 to-indigo-50">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-blue-600 text-white"><Gauge size={16} /></div>
          <div>
            <h3 className="panel-title">Speed & Section Control Analysis</h3>
            <p className="text-[11px] text-ink-faint">Haversine GPS • Optical Velocity • BSA 2023 Compliant • Court-Admissible</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data.is_overspeeding ? <span className="chip border-red-200 bg-red-600 text-white font-bold text-[10px]">{violationCount} VIOLATIONS DETECTED</span> : <span className="chip border-emerald-200 bg-emerald-600 text-white font-bold text-[10px]">✓ COMPLIANT • NO VIOLATION</span>}
          {data.bsa_compliant && <span className="chip border-blue-200 bg-blue-600 text-white font-bold text-[10px]"><FileCheck size={10} /> BSA 2023</span>}
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-4">
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink-faint">Total Distance</p>
          <p className="font-mono text-lg font-bold">{data.total_distance_km ?? 0} km</p>
          <p className="text-[11px] text-ink-faint">{data.total_duration_human ?? '—'} • {segments.length} segments</p>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink-faint">Average Speed</p>
          <p className="font-mono text-lg font-bold">{data.avg_speed_kmh ?? 0} km/h</p>
          <p className="text-[11px] text-ink-faint">Max {data.max_speed_kmh ?? 0} km/h • Limit {data.speed_limit_kmh ?? 80} km/h</p>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-ink-faint">Violations</p>
          <p className={`font-mono text-lg font-bold ${violationCount > 0 ? 'text-red-600' : 'text-emerald-600'}`}>{violationCount}</p>
          <p className="text-[11px] text-ink-faint">{data.critical_violations ?? 0} critical • Court: {data.court_admissible ? 'Yes' : 'No'}</p>
        </div>
        <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
          <p className="text-[10px] font-bold uppercase tracking-widest text-blue-700">Legal Compliance</p>
          <p className="font-mono text-[13px] font-bold text-blue-700">BSA 2023 Sec 63</p>
          <p className="text-[11px] text-blue-600">Sec 65B • SHA256 • Hash Chain</p>
        </div>
      </div>

      {segments.length > 0 && (
        <div className="border-t border-line">
          <div className="max-h-[320px] overflow-y-auto">
            <table className="data-table">
              <thead><tr><th>Route Segment</th><th>Distance</th><th>Duration</th><th>Avg Speed</th><th>Status</th><th>Evidence Hash</th></tr></thead>
              <tbody>
                {segments.map((seg, i) => (
                  <tr key={i} className={seg.is_violation ? 'bg-red-50/70' : ''}>
                    <td>
                      <div className="flex items-center gap-1 text-[11px]"><MapPin size={10} className="text-ink-faint" /><span className="font-mono font-bold">{seg.from_camera}</span><span>→</span><span className="font-mono font-bold">{seg.to_camera}</span></div>
                      <div className="text-[10px] text-ink-faint truncate max-w-[180px]">{seg.from_name} → {seg.to_name}</div>
                    </td>
                    <td className="font-mono text-xs font-semibold">{seg.distance_km} km</td>
                    <td><span className="flex items-center gap-1 text-xs"><Clock size={10} /> {seg.time_delta_human}</span></td>
                    <td>
                      <span className={`font-mono text-xs font-bold ${seg.is_violation ? 'text-red-600' : 'text-emerald-600'}`}>{seg.avg_speed_kmh} km/h</span>
                      {seg.is_violation && <div className="text-[10px] font-bold text-red-600">+{seg.overspeed_by_kmh} over limit</div>}
                    </td>
                    <td>{seg.is_violation ? <span className={`chip text-[10px] font-bold ${seg.severity === 'CRITICAL' ? 'bg-red-600 text-white border-red-700' : seg.severity === 'HIGH' ? 'bg-orange-500 text-white' : 'bg-amber-500 text-white'}`}>{seg.severity}</span> : <span className="chip border-emerald-200 bg-emerald-50 text-emerald-700 text-[10px] font-bold">✓ OK</span>}</td>
                    <td><span className="font-mono text-[10px] text-ink-faint">{seg.evidence_hash}</span>{seg.bsa_compliant && <Shield size={10} className="ml-1 inline text-blue-600" />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="border-t border-line bg-slate-50 px-4 py-3">
        <p className="text-[11px] leading-relaxed text-ink-muted">
          <span className="font-bold">Methodology:</span> Inter-camera section speed calculated via Haversine great-circle distance (GPS) divided by time delta (PTS-based). 
          Optical velocity via single-camera bbox centroid tracking with perspective calibration (15-78 km/h compliant range, &gt;80 km/h violation). 
          Each segment includes SHA256 evidence hash linked in chain, BSA 2023 Section 63 compliant certificate, and Section 65B Indian Evidence Act compliance for court admissibility. 
          Enables direct challan issuance for overspeeding.
        </p>
      </div>
    </div>
  );
}
