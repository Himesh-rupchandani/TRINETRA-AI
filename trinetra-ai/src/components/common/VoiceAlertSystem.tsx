import { useEffect, useRef, useState } from 'react';
import { Volume2, VolumeX } from 'lucide-react';
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
    const critical = active
      .filter(a => a.severity === 'CRITICAL' && a.status === 'NEW')
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0];
    if (!critical || critical.id === lastSpokenId) return;
    const utterance = new SpeechSynthesisUtterance(
      `Critical alert: Vehicle ${critical.plate} detected at ${critical.cameraId}.`
    );
    utterance.rate = 1;
    utterance.volume = 0.8;
    synthRef.current.cancel();
    synthRef.current.speak(utterance);
    setLastSpokenId(critical.id);
  }, [active, enabled, lastSpokenId]);

  return (
    <button
      onClick={() => setEnabled(!enabled)}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
        enabled ? 'border-slate-300 bg-slate-800 text-white' : 'border-line bg-surface-1 text-ink-faint hover:bg-surface-2'
      }`}
      title={enabled ? 'Audio alerts enabled' : 'Audio alerts disabled'}
    >
      {enabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
      <span className="hidden sm:inline">{enabled ? 'Audio On' : 'Audio Off'}</span>
    </button>
  );
}
