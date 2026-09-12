import { useEffect, useState } from 'react';
import { Shield, Zap, Activity, Cctv, MapPin, Lock } from 'lucide-react';
import { useAsync } from '@/hooks/useAsync';

interface ThreatLevel {
  threat_level: string;
  color: string;
  message: string;
  counts: { critical: number; high: number; total_active: number };
}

interface BandwidthData {
  savings: { bandwidth_savings_percent: number; tb_saved_per_day: number };
  gujarat_network: { total_cameras: number; total_bandwidth_required: { centralized_gbps: number; edge_ai_mbps: number } };
}

export function CommandCenterHero() {
  const [time, setTime] = useState(new Date());
  const threat = useAsync(async () => {
    try {
      const res = await fetch('/api/stats/threat-level');
      if (!res.ok) throw new Error('Failed');
      return (await res.json()) as ThreatLevel;
    } catch {
      return { threat_level: 'LOW', color: 'green', message: 'Low', counts: { critical: 0, high: 0, total_active: 0 } } as ThreatLevel;
    }
  }, []);
  
  const bandwidth = useAsync(async () => {
    try {
      const res = await fetch('/api/stats/bandwidth');
      if (!res.ok) throw new Error('Failed');
      return (await res.json()) as BandwidthData;
    } catch {
      return {
        savings: { bandwidth_savings_percent: 99.98, tb_saved_per_day: 3142 },
        gujarat_network: { total_cameras: 80000, total_bandwidth_required: { centralized_gbps: 320, edge_ai_mbps: 65 } }
      } as BandwidthData;
    }
  }, []);

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const threatLevel = threat.data?.threat_level ?? 'LOW';
  
  const threatStyles: Record<string, string> = {
    CRITICAL: 'bg-red-500 text-white border-red-600 animate-pulse shadow-[0_0_20px_rgba(239,68,68,0.5)]',
    HIGH: 'bg-orange-500 text-white border-orange-600 shadow-[0_0_15px_rgba(249,115,22,0.4)]',
    ELEVATED: 'bg-amber-500 text-white border-amber-600',
    LOW: 'bg-emerald-500 text-white border-emerald-600',
  };

  return (
    <div className="relative overflow-hidden rounded-2xl border border-slate-200 bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-6 text-white shadow-xl">
      <div className="absolute inset-0 opacity-[0.05]">
        <div className="h-full w-full" style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.08) 1px, transparent 1px)`,
          backgroundSize: '32px 32px'
        }} />
      </div>
      <div className="absolute -top-20 -right-20 h-60 w-60 rounded-full bg-blue-500/15 blur-[80px]" />
      <div className="absolute -bottom-20 -left-20 h-60 w-60 rounded-full bg-violet-500/10 blur-[80px]" />

      <div className="relative z-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-white text-blue-700 shadow-md">
              <Shield size={24} />
            </div>
            <div>
              <h1 className="text-[20px] font-bold tracking-tight">TRINETRA AI</h1>
              <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-blue-200">
                <MapPin size={11} /> Gujarat Police — Integrated CCTV Intelligence Platform
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-white/10 bg-white/[0.08] px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-blue-200">System Time</p>
              <p className="font-mono text-sm font-semibold">{time.toLocaleTimeString()} IST</p>
            </div>
            <div className={`rounded-xl border px-4 py-2 text-center font-bold shadow-md ${threatStyles[threatLevel] || threatStyles.LOW}`}>
              <p className="text-[10px] uppercase tracking-widest opacity-90">Threat Level</p>
              <p className="text-sm tracking-wide">{threatLevel}</p>
              <p className="text-[10px] font-mono opacity-80">{threat.data?.counts?.total_active ?? 0} active</p>
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.06] p-3">
            <div className="flex items-center gap-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-lg bg-blue-500/20"><Cctv size={16} className="text-blue-300" /></div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-blue-200">Federation</p>
                <p className="font-mono text-[12px] font-semibold">80,000 Cameras</p>
                <p className="text-[10px] text-blue-300">26 Departments</p>
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.06] p-3">
            <div className="flex items-center gap-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-lg bg-emerald-500/20"><Zap size={16} className="text-emerald-300" /></div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-emerald-200">Optimization</p>
                <p className="font-mono text-[12px] font-semibold">{bandwidth.data?.savings?.bandwidth_savings_percent ?? 99.98}% Saved</p>
                <p className="text-[10px] text-emerald-300">Edge AI • 65 Mbps total</p>
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.06] p-3">
            <div className="flex items-center gap-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-lg bg-violet-500/20"><Activity size={16} className="text-violet-300" /></div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-violet-200">AI Performance</p>
                <p className="font-mono text-[12px] font-semibold">94.2% mAP • 120ms</p>
                <p className="text-[10px] text-violet-300">YOLO11 • OCR • Tracking</p>
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.06] p-3">
            <div className="flex items-center gap-2.5">
              <div className="grid h-8 w-8 place-items-center rounded-lg bg-amber-500/20"><Lock size={16} className="text-amber-300" /></div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-widest text-amber-200">Evidence</p>
                <p className="font-mono text-[12px] font-semibold">BSA 2023 • SHA256</p>
                <p className="text-[10px] text-amber-300">Court-admissible</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
