import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Car } from 'lucide-react';
import { trafficService, type TrafficSession } from '@/services/trafficService';
import { config } from '@/lib/config';
import { Panel } from '@/components/common/Panel';

export function TrafficSessionsPanel() {
  const [items, setItems] = useState<TrafficSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (config.useMocks) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        if (document.hidden) return;
        const data = await trafficService.sessions(abort.signal);
        if (!abort.signal.aborted) { setItems(data.items); setError(null); }
      } catch (e) { if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'Traffic counts unavailable'); }
      finally { if (!abort.signal.aborted) timer = setTimeout(poll, 5000); }
    };
    void poll();
    return () => { abort.abort(); clearTimeout(timer); };
  }, []);
  if (config.useMocks) return null;
  return (
    <Panel title="Traffic observations — current camera sessions" icon={Car}>
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead><tr><th>Camera / source</th><th>Visible in last sample</th><th>Observed tracks</th><th>Crossings / entries</th><th>Car / Bike / Bus / Truck</th><th>Sampling</th></tr></thead>
          <tbody>{items.map(item => (
            <tr key={item.camera_id} data-traffic-camera={item.camera_id}>
              <td><Link className="font-semibold text-brand" to={`/cameras/${item.camera_id}`}>{item.camera_name}</Link><div className="text-[10px] text-ink-muted">{item.recorded ? 'Recorded video' : 'Camera capture'} · {item.status.toLowerCase()}{item.age_ms != null && item.age_ms > 5000 ? ' · stale' : ''}</div></td>
              <td className="font-mono">{item.visible_vehicles}</td><td className="font-mono">{item.observed_tracks}</td>
              <td className="font-mono">{item.config.mode === 'off' ? 'Not configured' : item.crossings}</td>
              <td className="font-mono">{item.by_class.car} / {item.by_class.motorcycle} / {item.by_class.bus} / {item.by_class.truck}{item.input_limited && <div className="text-[10px] text-degraded">Tracking budget reached</div>}</td>
              <td className="font-mono">{item.sample_hz ?? '—'} samples/s</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {!items.length && <p className="p-4 text-xs text-ink-muted">No observation session yet. Open a configured camera with detection on, or start its resident ingestion.</p>}
      {error && <p role="status" className="px-4 py-2 text-2xs text-degraded">{error} · retaining the last response.</p>}
      <p className="border-t border-line px-4 py-3 text-[10px] leading-relaxed text-ink-faint">Vehicle Log plate sightings and these traffic observations are different metrics. These are sampled, two-observation track counts — not total traffic or unique registrations. Sessions reset on scene/source changes, gaps and restart. Recorded and live sessions are not summed together.</p>
    </Panel>
  );
}
