import type { VehicleEvent } from '@/types';
import { get, http, isMockMode } from './api';
import { cameraDirectory, toVehicleEvent, type VehicleEventDto } from './adapters';

export type UploadJobStatus = 'IDLE' | 'QUEUED' | 'PROCESSING' | 'DONE' | 'FAILED';

/** One manually-uploaded CCTV video (= one demo camera) + its job state. */
export interface UploadedVideo {
  cameraId: string;
  name: string;
  location?: string | null;
  videoFile: string;
  status: string;
  jobStatus: UploadJobStatus;
  progressPct: number;
  framesTotal: number;
  framesProcessed: number;
  vehiclesSeen: number;
  platesRead: number;
  jobError?: string | null;
  note?: string | null;
  lastProcessedAt?: string | null;
}

export interface UploadedVideoDetail extends UploadedVideo {
  recentPlates: VehicleEvent[];
}

interface UploadedVideoDto {
  camera_id: string;
  name: string;
  location?: string | null;
  video_file: string;
  status: string;
  job_status: UploadJobStatus;
  progress_pct: number;
  frames_total: number;
  frames_processed: number;
  vehicles_seen: number;
  plates_read: number;
  job_error?: string | null;
  note?: string | null;
  last_processed_at?: string | null;
}

interface UploadedVideoDetailDto extends UploadedVideoDto {
  recent_plates?: VehicleEventDto[];
}

function toUploadedVideo(dto: UploadedVideoDto): UploadedVideo {
  return {
    cameraId: dto.camera_id,
    name: dto.name,
    location: dto.location,
    videoFile: dto.video_file,
    status: dto.status,
    jobStatus: dto.job_status,
    progressPct: dto.progress_pct,
    framesTotal: dto.frames_total,
    framesProcessed: dto.frames_processed,
    vehiclesSeen: dto.vehicles_seen,
    platesRead: dto.plates_read,
    jobError: dto.job_error,
    note: dto.note,
    lastProcessedAt: dto.last_processed_at,
  };
}

const MOCK_GUARD = 'Video upload needs the backend — start it and set VITE_USE_MOCKS=false.';

/**
 * Manually-uploaded CCTV videos (demo/test only — never live cameras).
 * Each upload becomes one camera (CAM1, CAM2, …) whose footage is decoded
 * and analysed by the backend's detection + ANPR pipeline.
 */
export const uploadService = {
  async nextCameraId(): Promise<string> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const res = await get<{ camera_id: string }>('/uploads/videos/next-camera-id');
    return res.camera_id;
  },

  async list(): Promise<UploadedVideo[]> {
    if (isMockMode) return [];
    const res = await get<UploadedVideoDto[]>('/uploads/videos');
    return (res ?? []).map(toUploadedVideo);
  },

  async upload(file: File, cameraId: string, name?: string): Promise<UploadedVideo> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const form = new FormData();
    form.append('file', file);
    form.append('camera_id', cameraId);
    if (name?.trim()) form.append('name', name.trim());
    // Uploads can be large: no client-side timeout beyond the default axios one.
    const res = await http.post<UploadedVideoDto>('/uploads/videos', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 0,
    });
    return toUploadedVideo(res.data);
  },

  async detail(cameraId: string): Promise<UploadedVideoDetail> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const [dto, dir] = await Promise.all([
      get<UploadedVideoDetailDto>(`/uploads/videos/${encodeURIComponent(cameraId)}`),
      cameraDirectory().catch(() => null),
    ]);
    return {
      ...toUploadedVideo(dto),
      recentPlates: (dto.recent_plates ?? []).map((e) => toVehicleEvent(e, dir)),
    };
  },

  async process(cameraId: string): Promise<UploadedVideo> {
    if (isMockMode) throw new Error(MOCK_GUARD);
    const res = await http.post<UploadedVideoDto>(
      `/uploads/videos/${encodeURIComponent(cameraId)}/process`,
    );
    return toUploadedVideo(res.data);
  },
};
