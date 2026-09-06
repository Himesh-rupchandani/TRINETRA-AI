import { useEffect, useState } from 'react';
import type { OfficerProfile } from '@/types';
import { officerService } from '@/services/officerService';

/**
 * The signed-in officer, shared by the sidebar and header profile areas.
 *
 * Cached at module level so both areas render the *same* officer photo from a
 * single request instead of fetching (or hard-coding) their own copy.
 */
let cached: OfficerProfile | null = null;
let inFlight: Promise<OfficerProfile> | null = null;

function loadCurrentOfficer(): Promise<OfficerProfile> {
  if (cached) return Promise.resolve(cached);
  if (!inFlight) {
    inFlight = officerService
      .current()
      .then((officer) => {
        cached = officer;
        return officer;
      })
      .finally(() => {
        inFlight = null;
      });
  }
  return inFlight;
}

/** Returns the current officer once loaded, or null while it resolves/fails. */
export function useCurrentOfficer(): OfficerProfile | null {
  const [officer, setOfficer] = useState<OfficerProfile | null>(cached);

  useEffect(() => {
    if (cached) return;
    let alive = true;
    loadCurrentOfficer()
      .then((res) => {
        if (alive) setOfficer(res);
      })
      .catch(() => {
        /* Non-critical chrome: fall back to the generic avatar icon. */
      });
    return () => {
      alive = false;
    };
  }, []);

  return officer;
}
