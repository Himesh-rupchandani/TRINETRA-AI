import { useEffect, useState } from 'react';
import { Cpu, Globe, MonitorSmartphone, ListTree, RefreshCcw, Play, Copy, Check } from 'lucide-react';
import { PageHeader } from '@/components/layout/PageHeader';
import { Panel } from '@/components/common/Panel';
import { CameraPlayer } from '@/components/camera/CameraPlayer';
import { useCameras } from '@/hooks/useCameras';
import { ingestService } from '@/services/ingestService';
import { cn } from '@/lib/utils';

export default function Ingest() {
  const { cameras, refresh: refreshCameras } = useCameras();
  const [selectedId, setSelectedId] = useState<string>('cam04');
  const [streams, setStreams] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [catalogue, setCatalogue] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [registryBusy, setRegistryBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; message: string } | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  const selectedCamera = cameras.find((c) => c.id === selectedId) ?? cameras[0] ?? null;

  useEffect(() => {
    if (cameras.length && !selectedId) {
      setSelectedId(cameras[0].id);
    }
  }, [cameras, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    setLoading(true);
    let cancelled = false;
    Promise.all([
      ingestService.streams(selectedId).catch(() => null),
      ingestService.health().catch(() => null),
      ingestService.catalogue(false).catch(() => null),
    ])
      .then(([s, h, cat]) => {
        if (cancelled) return;
        setStreams(s);
        setHealth(h);
        setCatalogue(cat?.raw ?? null);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedId, refreshTick]);

  const updateRegistry = async (restore: boolean) => {
    if (restore && !window.confirm('Restore missing CAM01–CAM30 camera entries? Existing settings, saved sightings and alerts will not be changed. This does not verify or start every feed.')) return;
    setRegistryBusy(true); setNotice(null);
    try {
      const result = restore ? await ingestService.restoreCameraList() : await ingestService.syncCatalogue();
      setNotice({ ok: result.status === 'success', message: result.message ?? (result.status === 'success' ? 'Camera list updated.' : 'Catalogue could not be synced; existing camera list was kept.') });
      if (result.status === 'success') refreshCameras();
      setRefreshTick(v => v+1);
    } catch (error) {
      setNotice({ ok: false, message: error instanceof Error ? error.message : 'Camera-list update failed.' });
    } finally { setRegistryBusy(false); }
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    });
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Unified Ingest API — All 4 Sentinel Streams"
        icon={ListTree}
        tone="blue"
        subtitle="RTSP AI • WHEP Browser • HLS Mobile • Camera directory — credentials stay server-side"
        actions={
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-ghost" disabled={registryBusy} onClick={() => void updateRegistry(false)}>
              <RefreshCcw size={12} /> Sync Catalogue
            </button>
            <button type="button" className="btn-ghost" disabled={registryBusy} onClick={() => void updateRegistry(true)}>
              Restore 30-camera list
            </button>
          </div>
        }
      />

      {notice && <p role="status" className={cn('mx-4 mt-3 rounded border p-3 text-xs', notice.ok ? 'border-online/40 text-online' : 'border-degraded/40 text-degraded')}>{notice.message}</p>}
      <div className="grid gap-4 p-4 sm:p-5 lg:grid-cols-12">
        {/* Left: Camera selector + live player */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          <Panel title="Select Camera (Hackathon Grid)" icon={ListTree}>
            <div className="max-h-[260px] overflow-auto p-2">
              <div className="grid grid-cols-3 gap-2">
                {cameras.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    className={cn(
                      'rounded border px-2 py-1.5 text-left text-xs transition',
                      selectedId === c.id
                        ? 'border-brand bg-brand/10 text-brand font-semibold'
                        : 'border-line hover:border-brand/40 hover:bg-surface-2',
                    )}
                  >
                    <div className="font-mono font-bold">{c.name}</div>
                    <div className="truncate text-2xs text-ink-faint">{c.location}</div>
                  </button>
                ))}
              </div>
            </div>
          </Panel>

          {selectedCamera && (
            <Panel
              title={`Live Preview — ${selectedCamera.name}`}
              icon={Play}
              actions={
                <span className="chip border-online/30 bg-online/10 text-online text-2xs">PLAYBACK PREVIEW</span>
              }
            >
              <CameraPlayer camera={selectedCamera} autoRequest />
              <p className="px-3 py-2 text-2xs text-ink-faint">
                Uses WHEP API: <code>/sentinel/stream/{selectedId}/whep</code> → proxy →{' '}
                <code>http://103.250.160.189:8889/stream/{selectedId}/whep</code> with auto Basic Auth
              </p>
            </Panel>
          )}
        </div>

        {/* Right: 4 APIs */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          {/* Health */}
          <Panel title="Ingest Health — All 4 APIs" icon={ListTree}>
            {health ? (
              <div className="grid grid-cols-2 gap-3 p-4 text-xs">
                <div>
                  <span className="text-ink-faint">Credentials:</span>{' '}
                  <span className={health.credentials_configured ? 'text-online' : 'text-critical'}>
                    {health.credentials_configured ? '✅ Configured (auto-login)' : '❌ Missing'}
                  </span>
                </div>
                <div>
                  <span className="text-ink-faint">Catalogue:</span>{' '}
                  <span className={health.catalogue_reachable ? 'text-online' : 'text-degraded'}>
                    {health.catalogue_reachable ? '✅ Reachable' : `⚠️ ${health.catalogue_error ?? 'Unreachable'}`}
                  </span>
                </div>
                <div>
                  <span className="text-ink-faint">Total Cameras:</span> {health.total_cameras}
                </div>
                <div>
                  <span className="text-ink-faint">Host:</span> {health.sentinel_host}:{health.rtsp_port}
                </div>
                <div className="col-span-2 mt-2 rounded bg-surface-2 p-2 font-mono text-2xs">
                  {JSON.stringify(health.apis, null, 2)}
                </div>
              </div>
            ) : (
              <p className="p-4 text-2xs text-ink-faint">{loading ? 'Loading...' : 'No health data'}</p>
            )}
          </Panel>

          {/* 4 API Cards */}
          <div className="grid gap-4 sm:grid-cols-2">
            {/* AI Processing RTSP */}
            <Panel title="🤖 AI Processing — RTSP" icon={Cpu} className="sm:col-span-2">
              <div className="space-y-2 p-4">
                <p className="text-xs text-ink-muted">
                  Backend CV engine consumes <code>rtsp://&lt;host&gt;:8554/stream/&lt;id&gt;</code> — authenticated URL built
                  server-side from <code>SENTINEL_EMAIL/PASSWORD</code>, never stored in DB or returned.
                </p>
                {streams ? (
                  <>
                    <div className="rounded border border-line bg-black p-2 font-mono text-2xs text-white/90">
                      <div className="flex items-center justify-between">
                        <span>{streams.streams.ai_processing.rtsp_public}</span>
                        <button
                          className="btn-ghost btn-xs"
                          onClick={() => copy(streams.streams.ai_processing.rtsp_public, 'rtsp')}
                        >
                          {copied === 'rtsp' ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                      </div>
                      <div className="mt-1 text-2xs text-white/60">
                        Redacted: {streams.streams.ai_processing.rtsp_authenticated_redacted}
                      </div>
                      <div className="mt-1 text-2xs text-white/60">
                        Ingest source (backend actual): {streams.streams.ai_processing.backend_ingest_source_redacted}
                      </div>
                    </div>
                    <p className="text-2xs text-ink-faint">
                      Usage: <code>{streams.usage.ai}</code>
                    </p>
                  </>
                ) : (
                  <p className="text-2xs text-ink-faint">Select a camera</p>
                )}
              </div>
            </Panel>

            {/* Browser Preview WHEP */}
            <Panel title="🌐 Browser Preview — WHEP" icon={Globe}>
              <div className="space-y-2 p-4">
                <p className="text-xs text-ink-muted">
                  Browser uses WebRTC WHEP: <code>http://&lt;host&gt;:8889/stream/&lt;id&gt;/whep</code> via same-origin proxy{' '}
                  <code>/sentinel/stream/&lt;id&gt;/whep</code> — Basic Auth injected server-side.
                </p>
                {streams ? (
                  <>
                    <div className="rounded border border-line bg-surface-2 p-2 font-mono text-2xs">
                      <div>Gateway: {streams.streams.browser_preview.whep_gateway}</div>
                      <div className="mt-1 flex items-center justify-between">
                        <span>Same-origin: {streams.streams.browser_preview.whep_same_origin}</span>
                        <button
                          className="btn-ghost btn-xs"
                          onClick={() => copy(streams.streams.browser_preview.whep_same_origin, 'whep')}
                        >
                          {copied === 'whep' ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                      </div>
                    </div>
                    <p className="text-2xs text-ink-faint">
                      Frontend: <code>{streams.usage.browser}</code>
                    </p>
                  </>
                ) : null}
              </div>
            </Panel>

            {/* Dashboard Mobile HLS */}
            <Panel title="📺 Dashboard/Mobile — HLS" icon={MonitorSmartphone}>
              <div className="space-y-2 p-4">
                <p className="text-xs text-ink-muted">
                  HLS fallback: <code>http://&lt;host&gt;/live/stream/&lt;id&gt;/index.m3u8</code> — via{' '}
                  <code>/sentinel/live/stream/&lt;id&gt;/index.m3u8</code> proxy.
                </p>
                {streams ? (
                  <>
                    <div className="rounded border border-line bg-surface-2 p-2 font-mono text-2xs">
                      <div>Live gateway: {streams.streams.dashboard_mobile.hls_live_gateway}</div>
                      <div className="mt-1">Same-origin: {streams.streams.dashboard_mobile.hls_live_same_origin}</div>
                      <div className="mt-1">CDN: {streams.streams.dashboard_mobile.hls_cdn}</div>
                      <div className="mt-1 flex items-center justify-between">
                        <span>Use: {streams.streams.dashboard_mobile.hls_live_same_origin}</span>
                        <button
                          className="btn-ghost btn-xs"
                          onClick={() => copy(streams.streams.dashboard_mobile.hls_live_same_origin, 'hls')}
                        >
                          {copied === 'hls' ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                      </div>
                    </div>
                    <p className="text-2xs text-ink-faint">
                      Frontend: <code>{streams.usage.hls}</code>
                    </p>
                  </>
                ) : null}
              </div>
            </Panel>

            {/* Catalogue */}
            <Panel title="📋 Camera Catalogue — /api/ingest" icon={ListTree} className="sm:col-span-2">
              <div className="space-y-2 p-4">
                <p className="text-xs text-ink-muted">
                  Catalogue API: <code>http://&lt;host&gt;/api/ingest</code> — lists all cameras, syncs from Sentinel{' '}
                  <code>https://cctv.corp8.cloud/cameras.json</code>
                </p>
                <div className="grid grid-cols-2 gap-2 font-mono text-2xs">
                  <div className="rounded bg-surface-2 p-2">
                    <div className="font-bold">GET /api/ingest</div>
                    <div className="text-ink-faint">Overview of all 4 APIs</div>
                  </div>
                  <div className="rounded bg-surface-2 p-2">
                    <div className="font-bold">GET /api/ingest/catalogue</div>
                    <div className="text-ink-faint">List cameras (DB)</div>
                  </div>
                  <div className="rounded bg-surface-2 p-2">
                    <div className="font-bold">GET /api/ingest/catalogue?sync=true</div>
                    <div className="text-ink-faint">Sync from Sentinel</div>
                  </div>
                  <div className="rounded bg-surface-2 p-2">
                    <div className="font-bold">GET /api/ingest/streams/{'{id}'}</div>
                    <div className="text-ink-faint">All 4 URLs for one camera</div>
                  </div>
                  <div className="rounded bg-surface-2 p-2">
                    <div className="font-bold">GET /api/ingest/preview/{'{id}'}</div>
                    <div className="text-ink-faint">WHEP ticket</div>
                  </div>
                  <div className="rounded bg-surface-2 p-2">
                    <div className="font-bold">GET /api/ingest/hls/{'{id}'}</div>
                    <div className="text-ink-faint">HLS URLs</div>
                  </div>
                </div>
                {catalogue && (
                  <div className="mt-2 text-2xs text-ink-faint">
                    Catalogue source: {catalogue.source} • Total: {catalogue.total_cameras} cameras
                  </div>
                )}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
