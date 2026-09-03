import { useCallback, useState } from 'react';
import { vehicleService } from '@/services/vehicleService';
import type { VehicleEvent, VehicleProfile, VehicleRoute } from '@/types';
import { isValidPlate, normalisePlate } from '@/lib/utils';

export interface TraceResult {
  plate: string;
  profile: VehicleProfile | null;
  events: VehicleEvent[];
  route: VehicleRoute | null;
}

/**
 * HERO FEATURE — registration number to full movement history.
 * One call fans out to profile + sightings + reconstructed GIS route.
 */
export function useVehicleSearch() {
  const [result, setResult] = useState<TraceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const trace = useCallback(async (raw: string): Promise<TraceResult | null> => {
    const plate = normalisePlate(raw);
    if (!plate) {
      setError('Enter a registration number to trace.');
      return null;
    }
    if (!isValidPlate(plate)) {
      setError(`"${raw}" is not a valid registration format (e.g. GJ01AB1234).`);
      setResult(null);
      setSearched(true);
      return null;
    }

    setLoading(true);
    setError(null);
    try {
      const [profile, events, route] = await Promise.all([
        vehicleService.profile(plate),
        vehicleService.events(plate),
        vehicleService.route(plate),
      ]);
      const next: TraceResult = { plate, profile, events, route };
      setResult(next);
      setSearched(true);
      return next;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Trace failed');
      setResult(null);
      setSearched(true);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
    setSearched(false);
  }, []);

  return { result, loading, error, searched, trace, reset };
}
