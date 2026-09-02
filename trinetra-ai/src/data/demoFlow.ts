import { Bell, Car, Cctv, Map } from 'lucide-react';
import type { TileTone } from '@/components/common/IconTile';

/**
 * The four things an officer does most often, in the order they usually do
 * them. Doubles as the guided demo walkthrough.
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
    label: 'Watch a Camera',
    to: '/cameras/cam04',
    hint: 'Open live view of any camera',
    icon: Cctv,
    tone: 'blue',
  },
  {
    step: 2,
    label: 'Look Up a Vehicle',
    to: `/vehicles/${DEMO_PLATE}`,
    hint: 'See everywhere a vehicle has been seen',
    icon: Car,
    tone: 'green',
  },
  {
    step: 3,
    label: 'See Route on Map',
    to: `/gis?plate=${DEMO_PLATE}`,
    hint: 'Track vehicle route from camera to camera',
    icon: Map,
    tone: 'purple',
  },
  {
    step: 4,
    label: 'Check Alerts',
    to: '/alerts',
    hint: 'View and confirm active alerts',
    icon: Bell,
    tone: 'orange',
  },
];
