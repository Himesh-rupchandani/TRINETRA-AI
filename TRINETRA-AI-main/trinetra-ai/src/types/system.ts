export type ServiceStatus = 'HEALTHY' | 'DEGRADED' | 'OFFLINE';
export type ProcessingState = 'IDLE' | 'PROCESSING' | 'BACKLOGGED' | 'STOPPED';

export interface ServiceHealth {
  id: string;
  name: string;
  description: string;
  status: ServiceStatus;
  uptimePct: number;
  uptimeSince: string;
  lastHeartbeat: string;
  activeConnections: number;
  processingState: ProcessingState;
  queueDepth?: number;
  latencyMs?: number;
  latestError?: string | null;
  version?: string;
}

export interface SystemSummary {
  services: ServiceHealth[];
  ingestFps: number;
  eventsPerMinute: number;
  anprPerMinute: number;
  generatedAt: string;
}

export interface DashboardKpis {
  totalCameras: number;
  camerasOnline: number;
  camerasDegraded: number;
  camerasOffline: number;
  activeAlerts: number;
  vehicleDetections24h: number;
  anprReads24h: number;
  watchlistMatches24h: number;
}
