import { useAsync } from '@/hooks/useAsync';
import { apiUrl } from '@/services/api';
import { Brain, AlertTriangle, Activity, Eye } from 'lucide-react';

interface Insights {
  threat_level: { level: string; message: string; counts: { critical: number; high: number } };
  traffic_analysis: { total_events: number; peak_hours: { hour: number; count: number }[]; camera_hotspots: { camera_id: string; count: number }[]; insights: { title: string; description: string; severity: string }[] };
  crowd_density: { by_camera: { camera_id: string; vehicles_per_hour: number; density_level: string }[]; average_vph: number };
  system_health: { ai_models: Record<string, string>; processing: Record<string, string> };
}

export function AIInsightsDashboard() {
  const insights = useAsync(async () => {
    const res = await fetch(apiUrl('/stats/insights'));
    if (!res.ok) throw new Error(`Intelligence analytics responded ${res.status}`);
    return (await res.json()) as Insights;
  }, []);

  if (insights.loading) return <div className="panel p-6"><div className="skeleton h-32 w-full" /></div>;
  const d = insights.data;
  // No fabricated fallback: when the backend is unreachable the panel says so
  // instead of inventing a LOW threat level with zeroed traffic figures.
  if (!d) {
    return (
      <div className="panel overflow-hidden">
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-violet-600 text-white"><Brain size={14} /></div>
            <div>
              <h3 className="panel-title">Intelligence Analytics</h3>
              <p className="text-[11px] text-ink-faint">Anomaly detection • Density • Threat assessment</p>
            </div>
          </div>
        </div>
        <div className="p-4 text-[11px] text-ink-muted">
          Intelligence analytics are unavailable{insights.error ? ` (${insights.error})` : ''}. No figures are estimated locally.
        </div>
      </div>
    );
  }

  const threatColors: Record<string, string> = {
    CRITICAL: 'border-red-200 bg-red-50 text-red-700',
    HIGH: 'border-orange-200 bg-orange-50 text-orange-700',
    ELEVATED: 'border-amber-200 bg-amber-50 text-amber-700',
    LOW: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  };

  const threatLevel = d.threat_level?.level ?? 'LOW';
  const threatCounts = d.threat_level?.counts ?? { critical: 0, high: 0 };

  return (
    <div className="panel overflow-hidden">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-violet-600 text-white"><Brain size={14} /></div>
          <div>
            <h3 className="panel-title">Intelligence Analytics</h3>
            <p className="text-[11px] text-ink-faint">Anomaly detection • Density • Threat assessment</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-3">
        <div className={`rounded-xl border p-3 ${threatColors[threatLevel] || threatColors.LOW}`}>
          <div className="flex items-center gap-1.5"><AlertTriangle size={14} /><p className="text-[11px] font-semibold uppercase tracking-widest">Threat Level</p></div>
          <p className="mt-1 font-bold">{threatLevel}</p>
          <p className="text-[11px] leading-snug opacity-90">{d.threat_level?.message ?? 'Monitoring'}</p>
          <div className="mt-2 flex gap-1.5"><span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-mono font-bold">{threatCounts.critical ?? 0} critical</span><span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-mono font-bold">{threatCounts.high ?? 0} high</span></div>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <div className="flex items-center gap-1.5"><Activity size={14} className="text-ink-faint" /><p className="text-[11px] font-semibold">Traffic</p></div>
          <p className="mt-1 font-mono font-bold">{d.traffic_analysis?.total_events ?? 0} events</p>
          <div className="mt-1.5 space-y-1">{(d.traffic_analysis?.peak_hours ?? []).slice(0, 2).map((p) => <div key={p.hour} className="flex justify-between text-[11px]"><span className="text-ink-faint">Peak {p.hour}:00</span><span className="font-mono font-semibold">{p.count}</span></div>)}</div>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <div className="flex items-center gap-1.5"><Eye size={14} className="text-ink-faint" /><p className="text-[11px] font-semibold">Density</p></div>
          <p className="mt-1 font-mono font-bold">{d.crowd_density?.average_vph ?? 0} vph avg</p>
          <div className="mt-1.5 space-y-1">{(d.crowd_density?.by_camera ?? []).slice(0, 2).map((c) => <div key={c.camera_id} className="flex justify-between text-[11px]"><span className="font-mono text-ink-faint">{c.camera_id}</span><span className="text-[10px] font-bold">{c.density_level}</span></div>)}</div>
        </div>
      </div>

      {(d.traffic_analysis?.insights?.length ?? 0) > 0 && (
        <div className="border-t border-line p-3">
          <p className="mb-2 text-[11px] font-semibold">Insights</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {(d.traffic_analysis?.insights ?? []).map((ins, i) => (
              <div key={i} className="rounded-lg border border-line bg-surface-2 p-2.5 text-[11px]">
                <p className="font-semibold">{ins.title}</p>
                <p className="text-ink-faint">{ins.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
