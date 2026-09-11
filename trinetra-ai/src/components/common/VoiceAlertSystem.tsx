import { useEffect, useRef, useState } from 'react';
import { Volume2, VolumeX, Radio } from 'lucide-react';
import { useAlerts } from '@/hooks/useAlerts';

export function VoiceAlertSystem() {
  const { active } = useAlerts();
  const [enabled, setEnabled] = useState(false);
  const [lastSpokenId, setLastSpokenId] = useState<string | null>(null);
  const synthRef = useRef<SpeechSynthesis | null>(null);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      synthRef.current = window.speechSynthesis;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !synthRef.current || active.length === 0) return;

    // Find latest critical alert not yet spoken
    const critical = active
      .filter(a => a.severity === 'CRITICAL' && a.status === 'NEW')
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0];

    if (!critical || critical.id === lastSpokenId) return;

    // Speak
    const utterance = new SpeechSynthesisUtterance(
      `Critical alert: Vehicle ${critical.plate} detected at ${critical.cameraId}. ${critical.category}. Immediate attention required.`
    );
    utterance.rate = 1.1;
    utterance.pitch = 1;
    utterance.volume = 0.9;
    
    synthRef.current.cancel();
    synthRef.current.speak(utterance);
    setLastSpokenId(critical.id);
  }, [active, enabled, lastSpokenId]);

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setEnabled(!enabled)}
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold transition-colors ${
          enabled 
            ? 'border-emerald-300 bg-emerald-500 text-white shadow-[0_0_10px_rgba(16,185,129,0.3)]' 
            : 'border-slate-200 bg-slate-100 text-slate-600'
        }`}
        title={enabled ? 'Voice alerts ON - critical alerts will be spoken' : 'Voice alerts OFF'}
      >
        {enabled ? <Volume2 size={14} className="animate-pulse" /> : <VolumeX size={14} />}
        <span className="hidden sm:inline">{enabled ? 'Voice ON' : 'Voice OFF'}</span>
        {enabled && <Radio size={10} className="animate-pulse" />}
      </button>
      {enabled && (
        <span className="hidden sm:inline text-[10px] text-ink-faint">
          🔊 Critical alerts spoken aloud
        </span>
      )}
    </div>
  );
}
