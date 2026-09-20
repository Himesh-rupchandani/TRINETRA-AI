/**
 * Unified Ingest Service — uses all 4 Sentinel APIs
 *
 * 🤖 AI processing      rtsp://<host>:8554/stream/<id>   — backend only, CV engine
 * 🌐 Browser preview    http://<host>:8889/stream/<id>/whep — WHEP WebRTC via /sentinel proxy
 * 📺 Dashboard/mobile   http://<host>/live/stream/<id>/index.m3u8 — HLS via /sentinel/live proxy
 * 📋 Camera catalogue   http://<host>/api/ingest/catalogue — camera list + sync
 *
 * All credentials auto-injected server-side (vite proxy + backend), never in bundle.
 */

import { get, post, isMockMode, backendUrl } from './api';
import * as mock from '@/mocks/mockBackend';
import type { Camera } from '@/types';
import { toCamera, type CameraItemDto } from './adapters';

interface CatalogueResponse {
  source: string;
  total_cameras: number;
  cameras: CameraItemDto[];
  catalogue_url?: string;
  synced?: boolean;
}

interface StreamsResponse {
  camera_id: string;
  camera_name: string;
  location: string;
  status: string;
  credentials_configured: boolean;
  streams: {
    ai_processing: {
      rtsp_public: string;
      rtsp_authenticated_redacted: string;
      example: string;
      backend_ingest_source_redacted: string;
    };
    browser_preview: {
      whep_gateway: string;
      whep_same_origin: string;
      example: string;
    };
    dashboard_mobile: {
      hls_live_gateway: string;
      hls_live_same_origin: string;
      hls_cdn: string;
      example: string;
    };
  };
  usage: {
    ai: string;
    browser: string;
    hls: string;
    catalogue: string;
  };
}

interface IngestHealth {
  credentials_configured: boolean;
  sentinel_host: string;
  rtsp_port: number;
  whep_origin: string;
  hls_base: string;
  catalogue_url: string;
  catalogue_reachable: boolean;
  total_cameras: number;
  apis: {
    ai_processing: string;
    browser_preview: string;
    dashboard_mobile: string;
    camera_catalogue: string;
  };
}

export const ingestService = {
  /**
   * 📋 Camera catalogue — GET /api/ingest/catalogue
   * Returns all cameras, optionally syncs from https://cctv.corp8.cloud/cameras.json
   */
  async catalogue(sync = false): Promise<{ cameras: Camera[]; raw: CatalogueResponse }> {
    if (isMockMode) {
      const cams = await mock.getCameras();
      return {
        cameras: cams,
        raw: {
          source: 'mock',
          total_cameras: cams.length,
          cameras: [] as any,
        },
      };
    }
    const res = await get<CatalogueResponse>(`/ingest/catalogue${sync ? '?sync=true' : ''}`);
    const cameras = (res.cameras ?? []).map(toCamera);
    return { cameras, raw: res };
  },

  /**
   * 📋 Sync catalogue — POST /api/ingest/sync
   * Triggers fetch from Sentinel catalogue URL
   */
  async syncCatalogue(): Promise<CatalogueResponse> {
    if (isMockMode) {
      const cams = await mock.getCameras();
      return {
        source: 'mock',
        total_cameras: cams.length,
        cameras: [] as any,
      };
    }
    return post<CatalogueResponse>('/ingest/sync');
  },

  /**
   * 🤖🌐📺 All streams for one camera — GET /api/ingest/streams/{id}
   * Returns RTSP (AI), WHEP (browser), HLS (mobile) URLs
   */
  async streams(cameraId: string): Promise<StreamsResponse> {
    if (isMockMode) {
      const id = cameraId.toLowerCase();
      return {
        camera_id: id,
        camera_name: `Camera ${id.toUpperCase()}`,
        location: 'Mock location',
        status: 'ONLINE',
        credentials_configured: true,
        streams: {
          ai_processing: {
            rtsp_public: `rtsp://103.250.160.189:8554/stream/${id}`,
            rtsp_authenticated_redacted: `rtsp://***:***@103.250.160.189:8554/stream/${id}`,
            example: `rtsp://<email>:<password>@103.250.160.189:8554/stream/${id}`,
            backend_ingest_source_redacted: `rtsp://103.250.160.189:8554/stream/${id}`,
          },
          browser_preview: {
            whep_gateway: `http://103.250.160.189:8889/stream/${id}/whep`,
            whep_same_origin: `/sentinel/stream/${id}/whep`,
            example: `http://103.250.160.189:8889/stream/${id}/whep`,
          },
          dashboard_mobile: {
            hls_live_gateway: `http://103.250.160.189/live/stream/${id}/index.m3u8`,
            hls_live_same_origin: `/sentinel/live/stream/${id}/index.m3u8`,
            hls_cdn: `https://cctv.corp8.cloud/${id}/index.m3u8`,
            example: `http://103.250.160.189/live/stream/${id}/index.m3u8`,
          },
        },
        usage: {
          ai: `cv-engine: python scripts/run_pipeline.py --mode live --camera ${id}`,
          browser: `useWhepStream('/sentinel/stream/${id}/whep', active)`,
          hls: `useHlsStream('/sentinel/live/stream/${id}/index.m3u8', active)`,
          catalogue: 'GET /api/ingest/catalogue?sync=true',
        },
      };
    }
    const res = await get<StreamsResponse>(`/ingest/streams/${encodeURIComponent(cameraId)}`);
    return { ...res, streams: { ...res.streams,
      browser_preview: { ...res.streams.browser_preview, whep_same_origin: backendUrl(res.streams.browser_preview.whep_same_origin) },
      dashboard_mobile: { ...res.streams.dashboard_mobile, hls_live_same_origin: backendUrl(res.streams.dashboard_mobile.hls_live_same_origin) },
    } };
  },

  /**
   * 🌐 Browser preview ticket — GET /api/ingest/preview/{id}
   */
  async preview(cameraId: string): Promise<{ whep_same_origin: string; whep_gateway: string }> {
    if (isMockMode) {
      const id = cameraId.toLowerCase();
      return {
        whep_same_origin: `/sentinel/stream/${id}/whep`,
        whep_gateway: `http://103.250.160.189:8889/stream/${id}/whep`,
      };
    }
    const res = await get<any>(`/ingest/preview/${encodeURIComponent(cameraId)}`);
    return { ...res.browser_preview, whep_same_origin: backendUrl(res.browser_preview.whep_same_origin) };
  },

  /**
   * 📺 HLS URLs — GET /api/ingest/hls/{id}
   */
  async hls(cameraId: string): Promise<{ live_gateway: string; live_same_origin: string; cdn: string }> {
    if (isMockMode) {
      const id = cameraId.toLowerCase();
      return {
        live_gateway: `http://103.250.160.189/live/stream/${id}/index.m3u8`,
        live_same_origin: `/sentinel/live/stream/${id}/index.m3u8`,
        cdn: `https://cctv.corp8.cloud/${id}/index.m3u8`,
      };
    }
    const res = await get<any>(`/ingest/hls/${encodeURIComponent(cameraId)}`);
    return { ...res.hls, live_same_origin: backendUrl(res.hls.live_same_origin) };
  },

  /**
   * Health of all 4 ingest APIs
   */
  async health(): Promise<IngestHealth> {
    if (isMockMode) {
      return {
        credentials_configured: true,
        sentinel_host: '103.250.160.189',
        rtsp_port: 8554,
        whep_origin: 'http://103.250.160.189:8889',
        hls_base: 'https://cctv.corp8.cloud',
        catalogue_url: 'https://cctv.corp8.cloud/cameras.json',
        catalogue_reachable: true,
        total_cameras: 30,
        apis: {
          ai_processing: 'rtsp://103.250.160.189:8554/stream/<id>',
          browser_preview: 'http://103.250.160.189:8889/stream/<id>/whep',
          dashboard_mobile: 'http://103.250.160.189/live/stream/<id>/index.m3u8',
          camera_catalogue: '/api/ingest/catalogue?sync=true',
        },
      };
    }
    return get<IngestHealth>('/ingest/health');
  },
};
