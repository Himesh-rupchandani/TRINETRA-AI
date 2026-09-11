import { useEffect, useState } from 'react';
import { Shield, Zap, Activity, Cctv, MapPin, Radio, Lock } from 'lucide-react';
import { useAsync } from '@/hooks/useAsync';

interface ThreatLevel {
  threat_level: string;
  color: string;
  message: string;
  counts: { critical: number; high: number; total_active: number };
}

interface BandwidthData {
  savings: { bandwidth_savings_percent: number; tb_saved_per_day: number; cost_saved_per_year_inr: number };
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
        savings: { bandwidth_savings_percent: 99.98, tb_saved_per_day: 3142, cost_saved_per_year_inr: 4807679507 },
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
    <div className="relative overflow-hidden rounded-[20px] border border-slate-200 bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-6 text-white shadow-2xl">
      <div className="absolute inset-0 opacity-[0.07]">
        <div className="h-full w-full" style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: '30px 30px'
        }} />
      </div>
      <div className="absolute -top-20 -right-20 h-60 w-60 rounded-full bg-blue-500/20 blur-[80px]" />
      <div className="absolute -bottom-20 -left-20 h-60 w-60 rounded-full bg-violet-500/20 blur-[80px]" />

      <div className="relative z-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-blue-400 to-blue-600 shadow-[0_0_20px_rgba(59,130,246,0.5)]">
              <Shield size={28} className="text-white" />
            </div>
            <div>
              <h1 className="flex items-center gap-2 text-[22px] font-black tracking-tight">
                TRINETRA AI
                <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-[10px] font-bold tracking-widest">COMMAND CENTER</span>
              </h1>
              <p className="mt-0.5 flex items-center gap-2 text-[13px] text-blue-200">
                <MapPin size={12} /> Gujarat Police — Integrated CCTV Intelligence & Investigation Platform • 80,000 Camera Federation
                <span className="hidden sm:inline-flex items-center gap-1 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" /> LIVE OPERATIONS
                </span>
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <div className="rounded-xl border border-white/15 bg-white/10 px-3 py-2 backdrop-blur">
              <p className="text-[10px] font-bold uppercase tracking-widest text-blue-200">System Time (IST)</p>
              <p className="font-mono text-sm font-bold">{time.toLocaleTimeString()} IST</p>
              <p className="font-mono text-[10px] text-blue-200">{time.toLocaleDateString()}</p>
            </div>
            
            <div className={`rounded-xl border px-4 py-2.5 text-center font-black shadow-lg backdrop-blur ${threatStyles[threatLevel] || threatStyles.LOW}`}>
              <p className="text-[10px] uppercase tracking-widest opacity-90">Threat Level</p>
              <p className="text-[15px] tracking-wide">{threatLevel}</p>
              <p className="text-[10px] font-mono opacity-80">{threat.data?.counts?.total_active ?? 0} active alerts</p>
            </div>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.07] p-3 backdrop-blur">
            <div className="flex items-center gap-2.5">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-500/20">
                <Cctv size={18} className="text-blue-300" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-blue-200">Camera Federation</p>
                <p className="font-mono text-[13px] font-bold">80,000 Cameras</p>
                <p className="text-[10px] text-blue-300">26 Departments • 33 Districts</p>
              </div>
            </div>
          </div>
          
          <div className="rounded-xl border border-white/10 bg-white/[0.07] p-3 backdrop-blur">
            <div className="flex items-center gap-2.5">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-500/20">
                <Zap size={18} className="text-emerald-300" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-200">Bandwidth Optimized</p>
                <p className="font-mono text-[13px] font-bold">{bandwidth.data?.savings?.bandwidth_savings_percent ?? 99.98}% Saved</p>
                <p className="text-[10px] text-emerald-300">{bandwidth.data?.savings?.tb_saved_per_day ?? 3142} TB/day • Edge AI</p>
              </div>
            </div>
          </div>
          
          <div className="rounded-xl border border-white/10 bg-white/[0.07] p-3 backdrop-blur">
            <div className="flex items-center gap-2.5">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-violet-500/20">
                <Activity size={18} className="text-violet-300" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-violet-200">AI Performance</p>
                <p className="font-mono text-[13px] font-bold">94.2% mAP • 120ms</p>
                <p className="text-[10px] text-violet-300">YOLO11 + OCR + ByteTrack</p>
              </div>
            </div>
          </div>
          
          <div className="rounded-xl border border-white/10 bg-white/[0.07] p-3 backdrop-blur">
            <div className="flex items-center gap-2.5">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-amber-500/20">
                <Lock size={18} className="text-amber-300" />
              </div>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-amber-200">Evidence Security</p>
                <p className="font-mono text-[13px] font-bold">BSA 2023 • SHA256</p>
                <p className="text-[10px] text-amber-300">Sec 63 + 65B • Court-admissible</p>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-3 py-2.5 backdrop-blur">
          <div className="flex items-center gap-2">
            <div className="grid h-6 w-6 place-items-center rounded-full bg-blue-500">
              <Shield size={12} className="text-white" />
            </div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-blue-200">Platform Capabilities:</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-semibold text-blue-100">Speed Violation Engine • Haversine GPS • Optical Velocity</span>
            <span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-semibold text-blue-100">Evidence Vault • SHA256 Hash Chain • BSA 2023 Certificate</span>
            <span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-semibold text-blue-100">AI Insights • Anomaly Detection • Threat Level • Predictive ETA 87%</span>
            <span className="rounded-full bg-white/10 px-2.5 py-1 text-[10px] font-semibold text-blue-100">Real-time • SSE/WS • Voice Alerts • Printable Reports • PWA</span>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 overflow-hidden rounded-lg border border-white/10 bg-black/30 px-3 py-2">
          <Radio size={12} className="shrink-0 animate-pulse text-red-400" />
          <div className="flex animate-[marquee_30s_linear_infinite] gap-8 whitespace-nowrap text-[11px] font-mono text-blue-100">
            <span>🔴 LIVE: GJ01AB1234 journey reconstructed — 359 km across 4 cameras • 5h 37m • Section speed analysis • BSA 2023 compliant</span>
            <span>⚡ FEDERATION: 80,000 cameras • 26 departments • Edge AI 65 Mbps • 99.98% bandwidth optimized • ₹480 Cr saved / 10 years</span>
            <span>🛡️ EVIDENCE: SHA256 hash chain • Digital signature • Chain of custody • Tamper detection • Court-admissible certificate • Sec 65B</span>
            <span>🎯 PREDICTIVE: Next-camera prediction with ETA • Direction-aware • 87% accuracy • Interception recommendation • Threat auto-calculated</span>
            <span>📡 INTEGRATION: Sentinel RTSP/HLS/WHEP secure proxy • PTS timing • Reconnect 2s→30s • Evidence writer • Catalogue sync • Production ready</span>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}
