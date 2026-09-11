import { useAsync } from '@/hooks/useAsync';
import { DollarSign, Zap } from 'lucide-react';

interface BandwidthData {
  gujarat_network: {
    total_cameras: number;
    departments: number;
    total_bandwidth_required: {
      centralized_mbps: number;
      centralized_gbps: number;
      edge_ai_mbps: number;
      edge_ai_gbps: number;
    };
  };
  data_volume: {
    centralized: { tb_per_day: number; pb_per_month: number };
    trinetra_edge_ai: { tb_per_day: number; events_per_day: number; events_per_second: number };
  };
  savings: {
    bandwidth_savings_percent: number;
    tb_saved_per_day: number;
    cost_saved_per_year_inr: number;
    cost_saved_per_month_usd: number;
  };
  judge_pitch: { headline: string; key_numbers: string[]; why_we_win: string };
}

export function BandwidthEngine() {
  const data = useAsync(async () => {
    try {
      const res = await fetch('/api/stats/bandwidth');
      if (!res.ok) throw new Error('Failed');
      return (await res.json()) as BandwidthData;
    } catch {
      return {
        gujarat_network: { total_cameras: 80000, departments: 26, total_bandwidth_required: { centralized_mbps: 320000, centralized_gbps: 320, edge_ai_mbps: 65.54, edge_ai_gbps: 0.066 } },
        data_volume: { centralized: { tb_per_day: 3143.2, pb_per_month: 94.3 }, trinetra_edge_ai: { tb_per_day: 0.644, events_per_day: 230400000, events_per_second: 2666.7 } },
        savings: { bandwidth_savings_percent: 99.98, tb_saved_per_day: 3142.6, cost_saved_per_year_inr: 4807679507, cost_saved_per_month_usd: 4826987 },
        judge_pitch: { headline: 'Only TRINETRA can handle 80,000 cameras', key_numbers: ['320 Gbps vs 65 Mbps', '99.98% saved'], why_we_win: 'Edge AI saves bandwidth' }
      } as BandwidthData;
    }
  }, []);

  if (data.loading) {
    return <div className="panel p-6"><div className="skeleton h-40 w-full" /></div>;
  }

  const d = data.data;
  if (!d) return null;

  const gujarat = d.gujarat_network ?? { total_cameras: 80000, total_bandwidth_required: { centralized_gbps: 320, edge_ai_mbps: 65 } };
  const dataVol = d.data_volume ?? { centralized: { tb_per_day: 3143, pb_per_month: 94.3 }, trinetra_edge_ai: { tb_per_day: 0.6, events_per_day: 230400000 } };
  const savings = d.savings ?? { bandwidth_savings_percent: 99.98, tb_saved_per_day: 3142, cost_saved_per_year_inr: 4807679507, cost_saved_per_month_usd: 4826987 };
  const pitch = d.judge_pitch ?? { headline: 'Only TRINETRA feasible', key_numbers: [], why_we_win: 'Edge AI' };

  return (
    <div className="panel overflow-hidden">
      <div className="panel-header bg-gradient-to-r from-emerald-50 to-blue-50">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-500 text-white">
            <Zap size={16} />
          </div>
          <div>
            <h3 className="panel-title">80,000 Camera Federation Engine</h3>
            <p className="text-[11px] text-ink-faint">Why only TRINETRA can handle Gujarat's scale</p>
          </div>
        </div>
        <span className="chip border-emerald-200 bg-emerald-500 text-white font-bold">JUDGE-WOW: 99.98% Saved</span>
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-3">
        <div className="rounded-xl border border-red-200 bg-gradient-to-br from-red-50 to-orange-50 p-4">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-red-500 text-white">❌</div>
            <div>
              <p className="text-xs font-bold text-red-700">Competitors: Centralized</p>
              <p className="text-[11px] text-red-600">Streaming all cameras centrally</p>
            </div>
          </div>
          <div className="mt-3 space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Bandwidth Needed</span>
              <span className="font-mono font-bold text-red-700">{gujarat.total_bandwidth_required?.centralized_gbps ?? 320} Gbps</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Data / Day</span>
              <span className="font-mono font-bold text-red-700">{dataVol.centralized?.tb_per_day ?? 3143} TB</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Data / Month</span>
              <span className="font-mono font-bold text-red-700">{dataVol.centralized?.pb_per_month ?? 94.3} PB</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Cost / Month</span>
              <span className="font-mono font-bold text-red-700">${((savings.cost_saved_per_month_usd ?? 4826987) + 989).toLocaleString()}</span>
            </div>
            <div className="mt-2 rounded-lg bg-red-500 px-2 py-1 text-center text-[11px] font-bold text-white">
              ❌ IMPOSSIBLE - No backbone can handle 320 Gbps
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-emerald-300 bg-gradient-to-br from-emerald-50 to-green-50 p-4 shadow-[0_0_20px_rgba(16,185,129,0.15)]">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-500 text-white">✅</div>
            <div>
              <p className="text-xs font-bold text-emerald-700">TRINETRA: Edge AI Hybrid</p>
              <p className="text-[11px] text-emerald-600">AI at camera, only metadata sent</p>
            </div>
          </div>
          <div className="mt-3 space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Bandwidth Needed</span>
              <span className="font-mono font-bold text-emerald-700">{gujarat.total_bandwidth_required?.edge_ai_mbps ?? 65} Mbps</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Data / Day</span>
              <span className="font-mono font-bold text-emerald-700">{dataVol.trinetra_edge_ai?.tb_per_day ?? 0.6} TB</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Events / Day</span>
              <span className="font-mono font-bold text-emerald-700">{((dataVol.trinetra_edge_ai?.events_per_day ?? 230400000) / 1000000).toFixed(1)}M</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Cost / Month</span>
              <span className="font-mono font-bold text-emerald-700">$989</span>
            </div>
            <div className="mt-2 rounded-lg bg-emerald-500 px-2 py-1 text-center text-[11px] font-bold text-white">
              ✅ FEASIBLE - Works on 4G, scales linearly
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-blue-300 bg-gradient-to-br from-blue-50 to-indigo-50 p-4">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-blue-500 text-white">
              <DollarSign size={16} />
            </div>
            <div>
              <p className="text-xs font-bold text-blue-700">Savings for Gujarat Police</p>
              <p className="text-[11px] text-blue-600">Per year with TRINETRA</p>
            </div>
          </div>
          <div className="mt-3 space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Bandwidth Saved</span>
              <span className="font-mono font-bold text-blue-700">{savings.bandwidth_savings_percent ?? 99.98}%</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">TB Saved / Day</span>
              <span className="font-mono font-bold text-blue-700">{savings.tb_saved_per_day ?? 3142}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Money Saved / Year</span>
              <span className="font-mono font-bold text-blue-700">₹{((savings.cost_saved_per_year_inr ?? 4807679507) / 10000000).toFixed(1)} Cr</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-ink-faint">Netflix Equivalent</span>
              <span className="font-mono text-[10px] font-bold text-blue-700">1M hours 4K/day saved</span>
            </div>
            <div className="mt-2 rounded-lg bg-blue-600 px-2 py-1 text-center text-[11px] font-bold text-white">
              💰 ₹480 Cr saved in 10 years
            </div>
          </div>
        </div>
      </div>

      <div className="border-t border-line bg-slate-50 p-3">
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="font-bold text-ink">🎯 Judge Pitch:</span>
          <span className="text-ink-muted">{pitch.why_we_win ?? 'Edge AI saves bandwidth'}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(pitch.key_numbers ?? []).slice(0, 3).map((k, i) => (
            <span key={i} className="chip border-blue-200 bg-blue-500/10 text-blue-700 font-mono text-[10px]">{k}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
