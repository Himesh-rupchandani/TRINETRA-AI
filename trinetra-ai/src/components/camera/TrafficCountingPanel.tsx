import { useEffect, useRef, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { trafficService, defaultTrafficConfig, type TrafficConfig, type TrafficSnapshot, type TrafficSettings, type CountingPreview } from '@/services/trafficService';
import { config } from '@/lib/config';
import { trafficConfigProblem } from '@/lib/traffic';
import { formatTime } from '@/lib/utils';

export function TrafficCountingPanel({ cameraId, traffic, onPreview }: {
  cameraId: string; traffic?: TrafficSnapshot | null; onPreview: (value: CountingPreview | null) => void;
}) {
  const [saved, setSaved] = useState<TrafficSettings | null>(null);
  const [draft, setDraft] = useState<TrafficConfig>(defaultTrafficConfig);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mounted = useRef(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    mounted.current = true;
    const abort = new AbortController();
    if (!config.useMocks) void trafficService.settings(cameraId, abort.signal).then((value) => {
      if (!abort.signal.aborted) { setError(null); setSaved(value); setDraft(value.config); onPreview({ config: value.config, draft: false }); }
    }).catch((e) => { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'Counting settings unavailable'); });
    return () => { mounted.current = false; abort.abort(); };
  }, [cameraId, onPreview, retry]);
  const dirty = saved && JSON.stringify(draft) !== JSON.stringify(saved.config);
  const update = (change: Partial<TrafficConfig>) => {
    const next = { ...draft, ...change };
    setDraft(next); setMessage(null);
    onPreview({ config: next, draft: JSON.stringify(next) !== JSON.stringify(saved?.config) });
  };
  const save = async () => {
    setBusy(true); setError(null);
    try {
      const value = await trafficService.save(cameraId, draft);
      if (!mounted.current) return;
      setSaved(value); setDraft(value.config); onPreview({ config: value.config, draft: false });
      setMessage('Saved. A fresh counting session starts with the next sample; plate sightings stay unchanged.');
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Save failed'); }
    finally { if (mounted.current) setBusy(false); }
  };
  const reset = async () => {
    if (!window.confirm('Reset this camera’s observation counters? Saved photos and plate sightings are not deleted.')) return;
    setBusy(true); setError(null);
    try {
      await trafficService.reset(cameraId);
      if (mounted.current) setMessage('Counter reset requested. Collection continues on the next sample; saved sightings are unchanged.');
    } catch (e) { if (mounted.current) setError(e instanceof Error ? e.message : 'Reset failed'); }
    finally { if (mounted.current) setBusy(false); }
  };
  if (config.useMocks) return null;
  const pending = saved && traffic && saved.revision !== traffic.config_revision;
  const invalid = trafficConfigProblem(draft);
  const numericField = (key: keyof TrafficConfig, label: string) => (
    <label className="space-y-1 text-2xs text-ink-muted" key={key}>
      <span className="flex justify-between">{label}<span className="font-mono">{Math.round(Number(draft[key])*100)}%</span></span>
      <input type="range" min="0" max="100" step="1" value={Math.round(Number(draft[key])*100)}
        aria-label={label} onChange={(event) => update({ [key]: Number(event.target.value)/100 })} className="w-full accent-cyan-500" />
    </label>
  );
  return (
    <section className="panel mt-3 overflow-hidden" aria-label="Traffic counting">
      <div className="panel-header"><h2 className="panel-title">Traffic observations · current session</h2><span className="text-2xs text-ink-muted">{traffic?.tracker === 'motion' ? 'Motion tracking' : traffic?.tracker === 'iou' ? 'IoU fallback' : 'Waiting for samples'}</span></div>
      <div className="space-y-3 p-3">
        <div className="grid grid-cols-3 gap-2 text-center">
          {[['Last sample', traffic?.visible_vehicles ?? '—'], ['Observed tracks', traffic?.observed_tracks ?? '—'], [traffic?.config.mode === 'zone' ? 'Zone entries' : 'Line crossings', traffic && traffic.config.mode !== 'off' ? traffic.crossings : 'Off']].map(([label,value]) => (
            <div key={label} className="rounded border border-line bg-surface-2 p-2"><p className="font-mono text-xl font-semibold text-ink">{value}</p><p className="text-[10px] text-ink-muted">{label}</p></div>
          ))}
        </div>
        {traffic && <p className="text-2xs text-ink-muted">Cars {traffic.by_class.car} · Bikes {traffic.by_class.motorcycle} · Buses {traffic.by_class.bus} · Trucks {traffic.by_class.truck}<br />
          Started {formatTime(traffic.started_at)} · {traffic.reset_reason} · {traffic.sample_hz ?? '—'} samples/s
        </p>}
        <p className="text-[10px] leading-relaxed text-ink-faint">Observed tracks need two samples. One qualifying crossing/entry per track. These sampled counts are not total traffic, plate reads or violations. Session resets on scene/source changes, gaps or restart.</p>
        {traffic?.input_limited && <p className="text-2xs text-degraded">Tracking budget reached; some vehicles were omitted.</p>}
        {traffic?.configuration_error && <p className="text-2xs text-critical">{traffic.configuration_error}</p>}
        {dirty && <p className="text-2xs text-degraded">Preview only — counters still use the saved settings until you save.</p>}
        {pending && <p className="text-2xs text-degraded">Saved settings are waiting for the next sample.</p>}
        <details className="border-t border-line pt-2">
          <summary className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-ink"><SlidersHorizontal size={12} /> Counting line / zone settings</summary>
          <fieldset disabled={!saved || busy} className="mt-3 space-y-3 disabled:opacity-50">
            <div className="grid gap-2 sm:grid-cols-3">
              <label className="text-2xs text-ink-muted">Rule<select aria-label="Counting rule" className="input mt-1 w-full" value={draft.mode} onChange={e => update({ mode: e.target.value as TrafficConfig['mode'] })}><option value="off">No crossing rule</option><option value="line">Line crossing</option><option value="zone">Zone entry</option></select></label>
              <label className="text-2xs text-ink-muted">Axis<select aria-label="Counting axis" className="input mt-1 w-full" value={draft.axis} onChange={e => update({ axis: e.target.value as TrafficConfig['axis'] })}><option value="horizontal">Horizontal line (up/down)</option><option value="vertical">Vertical line (left/right)</option></select></label>
              <label className="text-2xs text-ink-muted">Count direction<select aria-label="Count direction" className="input mt-1 w-full" value={draft.direction} onChange={e => update({ direction: e.target.value as TrafficConfig['direction'] })}><option value="both">Both directions</option><option value="positive">{draft.axis === 'horizontal' ? 'Down' : 'Right'}</option><option value="negative">{draft.axis === 'horizontal' ? 'Up' : 'Left'}</option></select></label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {draft.mode === 'line' && <>{numericField('position','Line position')}{numericField('span_start','Line span start')}{numericField('span_end','Line span end')}</>}
              {draft.mode === 'zone' && <>{numericField('left','Zone left')}{numericField('right','Zone right')}{numericField('top','Zone top')}{numericField('bottom','Zone bottom')}</>}
            </div>
            <p className="text-[10px] text-ink-faint">Positions are relative to the image, not screen pixels. Yellow overlay = unsaved preview; cyan = saved. Recalibrate after moving the camera. Rules only count — they never issue a violation alert.</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-ghost btn-xs" disabled={draft.mode === 'off' || Boolean(invalid)} onClick={() => document.getElementById('camera-live-player')?.scrollIntoView({behavior:'smooth',block:'center'})}>Preview on video</button>
              <button type="button" className="btn-solid btn-xs" disabled={!dirty || busy || Boolean(invalid)} onClick={save}>Save counting settings</button>
              <button type="button" className="btn-ghost btn-xs" disabled={!dirty || busy} onClick={() => { if (saved) { setDraft(saved.config); onPreview({config:saved.config,draft:false}); } }}>Cancel preview</button>
              <button type="button" className="btn-ghost btn-xs" disabled={!traffic || busy} onClick={reset}>Reset session counts</button>
            </div>
          </fieldset>
        </details>
        {invalid && <p role="alert" className="text-2xs text-critical">{invalid}</p>}
        {message && <p role="status" className="text-2xs text-online">{message}</p>}
        {error && <p role="alert" className="text-2xs text-critical">{error}</p>}
        {!saved && error && <button className="btn-ghost btn-xs" type="button" onClick={() => setRetry(v => v+1)}>Retry counting settings</button>}
      </div>
    </section>
  );
}
