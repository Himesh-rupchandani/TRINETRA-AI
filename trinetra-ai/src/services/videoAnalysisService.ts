import { get, http, isMockMode, post } from './api';

/* ------------------------------------------------------------------ types */

export type VideoStatus =
  | 'PENDING'
  | 'DOWNLOADING'
  | 'READY'
  | 'QUEUED'
  | 'PROCESSING'
  | 'DONE'
  | 'FAILED';

export type PlateStatus = 'HIGH' | 'LOW_CONFIDENCE' | 'UNKNOWN';

/** One video registered for multi-video analysis (upload or Google Drive). */
export interface AnalysisVideo {
  videoId: string;
  batchId?: string | null;
  cameraId: string;
  sourceType: 'UPLOAD' | 'GDRIVE';
  sourceName: string;
  sourceRef?: string | null;
  status: VideoStatus;
  error?: string | null;
  progressPct: number;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  durationSec?: number | null;
  durationLabel?: string | null;
  sizeBytes?: number | null;
  framesTotal: number;
  framesRead: number;
  framesAnalyzed: number;
  vehiclesDetected: number;
  platesRead: number;
  unknownPlates: number;
  createdAt?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
}

export interface AnalysisStatus {
  batchId?: string | null;
  status: 'EMPTY' | 'READY' | 'PROCESSING' | 'DONE' | 'PARTIAL' | 'FAILED';
  totalVideos: number;
  completedVideos: number;
  progressPct: number;
  videos: AnalysisVideo[];
}

export interface VehicleAppearance {
  camera_id: string;
  camera_label: string;
  video_id: string | null;
  source_name: string | null;
  source_type: string | null;
  detections: number;
  first_seen: string;
  first_seen_sec: number | null;
  last_seen: string;
  last_seen_sec: number | null;
  first_event_time: string;
  last_event_time: string;
  best_ocr_confidence: number;
  best_raw_ocr: string | null;
  best_event_id: number | null;
  plate_status: PlateStatus;
  vehicle_class: string | null;
  detection_confidence: number | null;
  track_ids: number[];
}

export interface VehicleHistoryStep {
  step: number;
  camera_id: string;
  camera_label: string;
  video_id: string | null;
  source_name: string | null;
  timestamp: string;
  timestamp_sec: number | null;
  last_seen: string;
  event_time: string;
  vehicle_class: string | null;
  detections: number;
  ocr_confidence: number;
  detection_confidence: number | null;
  plate_status: PlateStatus;
  raw_ocr: string | null;
  event_id: number | null;
}

export interface VehicleRecord {
  plate: string;
  normalized_plate: string;
  video_count: number;
  cameras: string[];
  sequence: string[];
  sequence_label: string;
  seen_in_multiple: boolean;
  total_detections: number;
  first_seen: { camera_id: string; camera_label: string; timestamp: string; event_time: string };
  last_seen: { camera_id: string; camera_label: string; timestamp: string; event_time: string };
  best_ocr_confidence: number;
  best_raw_ocr: string | null;
  best_detection_confidence: number | null;
  vehicle_class: string | null;
  plate_status: PlateStatus;
  appearances: VehicleAppearance[];
  history: VehicleHistoryStep[];
  sightings?: Sighting[];
}

export interface Sighting {
  event_id: number;
  video_id: string | null;
  camera_id: string;
  camera_label: string;
  source_name: string | null;
  plate: string;
  raw_ocr: string | null;
  ocr_confidence: number;
  plate_status: PlateStatus;
  vehicle_class: string | null;
  detection_confidence: number | null;
  track_id: number | null;
  frame_number: number | null;
  bbox: number[] | null;
  video_offset_sec: number | null;
  timestamp: string;
  event_time: string;
}

export interface PossibleMatch {
  plate_a: string;
  plate_b: string;
  differing_characters: number;
  confidence_a: number;
  confidence_b: number;
  status_a: PlateStatus;
  status_b: PlateStatus;
  combined_cameras: string[];
  match_type: 'fuzzy';
  verdict: string;
  note: string;
}

export interface AnalysisResults {
  batch_id: string | null;
  videos: Array<{
    video_id: string;
    camera_id: string;
    source_name: string;
    source_type: string;
    status: VideoStatus;
    vehicles_detected: number;
    plates_read: number;
  }>;
  total_videos: number;
  total_sightings: number;
  readable_sightings: number;
  unreadable_sightings: number;
  unique_plates: number;
  plates_in_multiple_videos: number;
  vehicles: VehicleRecord[];
  multi_video_vehicles: VehicleRecord[];
  possible_matches: PossibleMatch[];
}

export interface PlateSearchResult {
  query: string;
  normalized_query: string;
  found: boolean;
  match_type: 'exact' | null;
  vehicle: VehicleRecord | null;
  possible_matches: Array<{
    plate: string;
    differing_characters: number;
    video_count: number;
    cameras: string[];
    sequence_label: string;
    best_ocr_confidence: number;
    plate_status: PlateStatus;
    match_type: 'fuzzy';
    note: string;
  }>;
  sightings: Sighting[];
}

export interface DriveValidation {
  valid: boolean;
  accessible: boolean;
  fileId?: string;
  normalizedUrl?: string;
  fileName?: string | null;
  sizeBytes?: number | null;
  contentType?: string | null;
  reason?: string | null;
  suggestedCameraId?: string;
}

/* ------------------------------------------------------------------ dtos */

interface AnalysisVideoDto {
  video_id: string;
  batch_id?: string | null;
  camera_id: string;
  source_type: 'UPLOAD' | 'GDRIVE';
  source_name: string;
  source_ref?: string | null;
  status: VideoStatus;
  error?: string | null;
  progress_pct: number;
  fps?: number | null;
  width?: number | null;
  height?: number | null;
  duration_sec?: number | null;
  duration_label?: string | null;
  size_bytes?: number | null;
  frames_total: number;
  frames_read: number;
  frames_analyzed: number;
  vehicles_detected: number;
  plates_read: number;
  unknown_plates: number;
  created_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

function toVideo(d: AnalysisVideoDto): AnalysisVideo {
  return {
    videoId: d.video_id,
    batchId: d.batch_id,
    cameraId: d.camera_id,
    sourceType: d.source_type,
    sourceName: d.source_name,
    sourceRef: d.source_ref,
    status: d.status,
    error: d.error,
    progressPct: d.progress_pct,
    fps: d.fps,
    width: d.width,
    height: d.height,
    durationSec: d.duration_sec,
    durationLabel: d.duration_label,
    sizeBytes: d.size_bytes,
    framesTotal: d.frames_total,
    framesRead: d.frames_read,
    framesAnalyzed: d.frames_analyzed,
    vehiclesDetected: d.vehicles_detected,
    platesRead: d.plates_read,
    unknownPlates: d.unknown_plates,
    createdAt: d.created_at,
    startedAt: d.started_at,
    completedAt: d.completed_at,
  };
}

const MOCK_GUARD =
  'Video analysis needs the backend — start it and set VITE_USE_MOCKS=false in trinetra-ai/.env.';

/**
 * Multi-video analysis: upload local CCTV videos and/or add shared Google
 * Drive links, run the detection + ANPR pipeline over all of them, and compare
 * the number plates read across every video.
 *
 * Every figure returned here comes from real analysis of the submitted files —
 * there is no demo/sample path in this service.
 */
export const videoAnalysisService = {
  async list(batchId?: string): Promise<AnalysisVideo[]> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const res = await get<{ videos: AnalysisVideoDto[] }>('/analysis/videos', {
      params: batchId ? { batch_id: batchId } : undefined,
    });
    return (res.videos ?? []).map(toVideo);
  },

  async uploadFiles(
    files: File[],
    opts: { batchId?: string; cameraIds?: string[]; autoStart?: boolean } = {},
  ): Promise<{ batchId: string; added: AnalysisVideo[]; errors: Array<{ source_name: string; error: string }> }> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const form = new FormData();
    files.forEach((f) => form.append('files', f));
    if (opts.batchId) form.append('batch_id', opts.batchId);
    if (opts.cameraIds?.length) form.append('camera_ids', opts.cameraIds.join(','));
    form.append('auto_start', String(Boolean(opts.autoStart)));
    const res = await http.post<{
      batch_id: string;
      added: AnalysisVideoDto[];
      errors: Array<{ source_name: string; error: string }>;
    }>('/analysis/videos/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 0,
    });
    return {
      batchId: res.data.batch_id,
      added: (res.data.added ?? []).map(toVideo),
      errors: res.data.errors ?? [],
    };
  },

  async validateDriveLink(url: string): Promise<DriveValidation> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const res = await post<{
      valid: boolean;
      accessible: boolean;
      file_id?: string;
      normalized_url?: string;
      file_name?: string | null;
      size_bytes?: number | null;
      content_type?: string | null;
      reason?: string | null;
      suggested_camera_id?: string;
    }>('/analysis/videos/gdrive/validate', { url });
    return {
      valid: res.valid,
      accessible: res.accessible,
      fileId: res.file_id,
      normalizedUrl: res.normalized_url,
      fileName: res.file_name,
      sizeBytes: res.size_bytes,
      contentType: res.content_type,
      reason: res.reason,
      suggestedCameraId: res.suggested_camera_id,
    };
  },

  async addDriveVideo(url: string, cameraId?: string, batchId?: string): Promise<AnalysisVideo> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const res = await http.post<{ added: AnalysisVideoDto[] }>(
      '/analysis/videos/gdrive',
      { url, camera_id: cameraId || null, batch_id: batchId || null },
      { timeout: 0 },
    );
    return toVideo(res.data.added[0]);
  },

  async remove(videoId: string): Promise<void> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    await http.delete(`/analysis/videos/${encodeURIComponent(videoId)}`);
  },

  async run(videoIds?: string[]): Promise<void> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    await post('/analysis/run', { video_ids: videoIds ?? null });
  },

  async status(batchId?: string): Promise<AnalysisStatus> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const res = await get<{
      batch_id?: string | null;
      status: AnalysisStatus['status'];
      total_videos: number;
      completed_videos: number;
      progress_pct: number;
      videos: AnalysisVideoDto[];
    }>('/analysis/status', { params: batchId ? { batch_id: batchId } : undefined });
    return {
      batchId: res.batch_id,
      status: res.status,
      totalVideos: res.total_videos,
      completedVideos: res.completed_videos,
      progressPct: res.progress_pct,
      videos: (res.videos ?? []).map(toVideo),
    };
  },

  async results(batchId?: string): Promise<AnalysisResults> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    return get<AnalysisResults>('/analysis/results', {
      params: batchId ? { batch_id: batchId } : undefined,
    });
  },

  async search(plate: string, batchId?: string): Promise<PlateSearchResult> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    return get<PlateSearchResult>('/analysis/search', {
      params: { plate, ...(batchId ? { batch_id: batchId } : {}) },
    });
  },

  async history(plate: string, batchId?: string): Promise<VehicleRecord> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    return get<VehicleRecord>(`/analysis/vehicles/${encodeURIComponent(plate)}`, {
      params: batchId ? { batch_id: batchId } : undefined,
    });
  },
};

/* --------------------------------------------------- plate usage (time in shot) */

/** One continuous stretch of time a vehicle was tracked in the video. */
export interface PlateUsageSegment {
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  start: string;
  end: string;
  track_id: number | null;
}

/** One number plate, with how long it was in shot. */
export interface PlateUsageRow {
  plate: string | null;
  plate_label: string;
  vehicle_class: string | null;
  plate_status: PlateStatus;
  best_plate_confidence: number | null;
  best_detection_confidence: number | null;

  /** How many separate times it entered the shot. */
  appearances: number;
  first_seen_sec: number;
  last_seen_sec: number;
  first_seen: string;
  last_seen: string;

  /** Span from first sighting to last (time in the area). HH:MM:SS. */
  dwell_sec: number;
  dwell_label: string;
  /** Time actually tracked on screen. Always <= dwell_sec. */
  visible_sec: number;
  visible_label: string;
  /** Share of the video's duration this plate was present for. */
  presence_pct: number | null;

  frames_present: number;
  track_ids: Array<number | null>;
  evidence_ref: string | null;
  watchlist_match: boolean;
  segments: PlateUsageSegment[];
}

export interface PlateUsageReport {
  video: {
    video_id: string;
    camera_id: string;
    source_name: string;
    source_type: string;
    status: string;
    error: string | null;
    progress_pct: number;
    duration_sec: number | null;
    duration_label: string | null;
    fps: number | null;
    vehicles_detected: number;
    plates_read: number;
    unknown_plates: number;
  };
  summary: {
    appearances: number;
    unique_plates: number;
    unreadable_vehicles: number;
    total_dwell_sec: number;
    total_dwell_label: string;
    longest_dwell_sec: number;
    longest_dwell_label: string;
    longest_plate: string | null;
    watchlist_hits: number;
    video_duration_sec: number | null;
  };
  plates: PlateUsageRow[];
  unreadable: PlateUsageRow[];
  notes: string[];
}

const PLATE_USAGE_GUARD =
  'Plate usage needs the backend — start it and set VITE_USE_MOCKS=false in trinetra-ai/.env.';

export const plateUsageService = {
  /** Per-plate time-in-shot report. Omit videoId to use the latest video. */
  async report(videoId?: string): Promise<PlateUsageReport> {
    if (isMockMode) throw new Error(PLATE_USAGE_GUARD);
    return get<PlateUsageReport>('/analysis/plate-usage', {
      params: videoId ? { video_id: videoId } : undefined,
    });
  },

  /** Absolute URL of the CSV export (use as a download href). */
  csvUrl(videoId?: string): string {
    const base = http.defaults.baseURL ?? '';
    const qs = videoId ? `?video_id=${encodeURIComponent(videoId)}` : '';
    return `${base}/analysis/plate-usage.csv${qs}`;
  },
};
