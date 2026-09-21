import { apiAssetUrl } from '@/services/api';
import { useAsync } from '@/hooks/useAsync';
import { Server, Cpu, BarChart3 } from 'lucide-react';

interface BandwidthData {
  gujarat_network: {
    total_cameras: number;
    total_bandwidth_required: { centralized_gbps: number; edge_ai_mbps: number };
  };
  data_volume: {
    centralized: { tb_per_day: number; pb_per_month: number };
    trinetra_edge_ai: { tb_per_day: number; events_per_day: number };
  };
  savings: { bandwidth_savings_percent: number; tb_saved_per_day: number };
  federation: { edge_nodes_required: number; central_servers_required: number; scalability: string };
}

// Shape tolerance only: a missing key renders as 0 / "—", never as an invented
// figure. The panel used to ship a full fake payload in its `catch` (and the
// same numbers again as `??` fallbacks), so when /api/stats/bandwidth failed the
// dashboard still "reported" 320 Gbps, 94.3 PB/month and 1600 edge nodes as if
// they had come from the engine.
const EMPTY: BandwidthData = {
  gujarat_network: { total_cameras: 0, total_bandwidth_required: { centralized_gbps: 0, edge_ai_mbps: 0 } },
  data_volume: { centralized: { tb_per_day: 0, pb_per_month: 0 }, trinetra_edge_ai: { tb_per_day: 0, events_per_day: 0 } },
  savings: { bandwidth_savings_percent: 0, tb_saved_per_day: 0 },
  federation: { edge_nodes_required: 0, central_servers_required: 0, scalability: '' },
};

export function BandwidthEngine() {
  const data = useAsync(async () => {
    const res = await fetch(apiAssetUrl('/stats/bandwidth'));
    if (!res.ok) throw new Error(`Bandwidth engine responded ${res.status}`);
    const json = (await res.json()) as Partial<BandwidthData>;
    return {
      gujarat_network: { ...EMPTY.gujarat_network, ...(json.gujarat_network ?? {}) },
      data_volume: {
        centralized: { ...EMPTY.data_volume.centralized, ...(json.data_volume?.centralized ?? {}) },
        trinetra_edge_ai: { ...EMPTY.data_volume.trinetra_edge_ai, ...(json.data_volume?.trinetra_edge_ai ?? {}) },
      },
      savings: { ...EMPTY.savings, ...(json.savings ?? {}) },
      federation: { ...EMPTY.federation, ...(json.federation ?? {}) },
    } as BandwidthData;
  }, []);

  if (data.loading) return <div className="panel p-6"><div className="skeleton h-32 w-full" /></div>;
  const d = data.data;
  if (!d) {
    // Honest failure state: no projection numbers are shown at all.
    return (
      <div className="panel overflow-hidden">
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <div className="grid h-7 w-7 place-items-center rounded-lg bg-slate-800 text-white"><BarChart3 size={14} /></div>
            <div>
              <h3 className="panel-title">Federation Architecture</h3>
              <p className="text-[11px] text-ink-faint">Bandwidth projection unavailable</p>
            </div>
          </div>
        </div>
        <div className="p-4 text-[11px] text-ink-muted">
          The bandwidth engine did not return data{data.error ? ` (${data.error})` : ''}.
          No figures are estimated locally.
        </div>
      </div>
    );
  }

  const gujarat = d.gujarat_network;
  const dataVol = d.data_volume;
  const savings = d.savings;
  const federation = d.federation;

  return (
    <div className="panel overflow-hidden">
      <div className="panel-header">
        <div className="flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-lg bg-slate-800 text-white"><BarChart3 size={14} /></div>
          <div>
            <h3 className="panel-title">Federation Architecture</h3>
            <p className="text-[11px] text-ink-faint">80,000 cameras • Edge AI Hybrid • Bandwidth optimized</p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 p-4 sm:grid-cols-3">
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <div className="flex items-center gap-2"><Server size={14} className="text-ink-faint" /><p className="text-[11px] font-semibold">Traditional Centralized</p></div>
          <div className="mt-2.5 space-y-1.5 text-xs">
            <div className="flex justify-between"><span className="text-ink-faint">Bandwidth</span><span className="font-mono font-semibold">{gujarat.total_bandwidth_required?.centralized_gbps ?? 0} Gbps</span></div>
            <div className="flex justify-between"><span className="text-ink-faint">Data/Day</span><span className="font-mono">{dataVol.centralized?.tb_per_day ?? 0} TB</span></div>
            <div className="flex justify-between"><span className="text-ink-faint">Data/Month</span><span className="font-mono">{dataVol.centralized?.pb_per_month ?? 0} PB</span></div>
          </div>
        </div>
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-3">
          <div className="flex items-center gap-2"><Cpu size={14} className="text-emerald-700" /><p className="text-[11px] font-semibold text-emerald-800">TRINETRA Edge AI</p></div>
          <div className="mt-2.5 space-y-1.5 text-xs">
            <div className="flex justify-between"><span className="text-ink-faint">Bandwidth</span><span className="font-mono font-semibold text-emerald-700">{gujarat.total_bandwidth_required?.edge_ai_mbps ?? 0} Mbps</span></div>
            <div className="flex justify-between"><span className="text-ink-faint">Data/Day</span><span className="font-mono font-semibold text-emerald-700">{dataVol.trinetra_edge_ai?.tb_per_day ?? 0} TB</span></div>
            <div className="flex justify-between"><span className="text-ink-faint">Events/Day</span><span className="font-mono font-semibold text-emerald-700">{((dataVol.trinetra_edge_ai?.events_per_day ?? 0) / 1000000).toFixed(1)}M</span></div>
          </div>
        </div>
        <div className="rounded-xl border border-line bg-surface-2 p-3">
          <div className="flex items-center gap-2"><BarChart3 size={14} className="text-ink-faint" /><p className="text-[11px] font-semibold">Optimization</p></div>
          <div className="mt-2.5 space-y-1.5 text-xs">
            <div className="flex justify-between"><span className="text-ink-faint">Saved</span><span className="font-mono font-semibold">{savings.bandwidth_savings_percent ?? 0}%</span></div>
            <div className="flex justify-between"><span className="text-ink-faint">Edge Nodes</span><span className="font-mono">{federation.edge_nodes_required ?? 0}</span></div>
            <div className="flex justify-between"><span className="text-ink-faint">Central HA</span><span className="font-mono">{federation.central_servers_required ?? 0} servers</span></div>
          </div>
        </div>
      </div>
      <div className="border-t border-line bg-surface-2 px-4 py-2.5 text-[11px] text-ink-muted">
        Edge AI processes YOLO11 locally, sends only 2.5KB metadata per detection vs 4 Mbps continuous. {federation.scalability || 'Linear scaling'} • Resilient • &lt;2 sec alerts.
      </div>
    </div>
  );
}
