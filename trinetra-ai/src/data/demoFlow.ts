import { Car, Cctv, ListTree, Map, Video } from 'lucide-react';
import type { TileTone } from '@/components/common/IconTile';

/**
 * The core investigation workflow, in the order an officer follows it:
 * analyse a video → watch live cameras → look up a vehicle →
 * see its route on the map → check the vehicle log.
 * Used by the dashboard workflow strip and the hero task grid.
 */
export interface DemoStep {
  step: number;
  label: string;
  to: string;
  hint: string;
  icon: typeof Cctv;
  tone: TileTone;
}

export const DEMO_PLATE = 'GJ01AB1234';

export const demoFlow: DemoStep[] = [
  {
    step: 1,
    label: 'Analyse a Video',
    to: '/video-analysis',
    hint: 'Upload CCTV footage, detect vehicles & plates',
    icon: Video,
    tone: 'blue',
  },
  {
    step: 2,
    label: 'Watch Live Cameras',
    to: '/cameras',
    hint: 'Open live feeds from any camera',
    icon: Cctv,
    tone: 'green',
  },
  {
    step: 3,
    label: 'Look Up a Vehicle',
    to: `/vehicles/${DEMO_PLATE}`,
    hint: 'See everywhere a vehicle has been seen',
    icon: Car,
    tone: 'sky',
  },
  {
    step: 4,
    label: 'See Route on Map',
    to: `/gis?plate=${DEMO_PLATE}`,
    hint: 'Track vehicle route from camera to camera',
    icon: Map,
    tone: 'orange',
  },
  {
    step: 5,
    label: 'Check Vehicle Log',
    to: '/events',
    hint: 'Full detection history with time & place',
    icon: ListTree,
    tone: 'purple',
  },
];
