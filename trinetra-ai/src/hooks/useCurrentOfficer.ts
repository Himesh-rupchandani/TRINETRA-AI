import { useSyncExternalStore } from 'react';
import type { OfficerProfile } from '@/types';
import { officerService } from '@/services/officerService';

/**
 * ACTIVE OFFICER STORE
 * --------------------
 * One module-level store shared by every profile area (sidebar, header,
 * Profile page) so switching officer updates all of them at once, from a
 * single fetch. The selection is remembered across reloads.
 */

export interface OfficerState {
  /** Officer whose data the whole app is currently showing. */
  current: OfficerProfile | null;
  /** Officers the control room can switch between. */
  roster: OfficerProfile[];
  loading: boolean;
  error: string | null;
}

const STORAGE_KEY = 'trinetra.officer';

let state: OfficerState = { current: null, roster: [], loading: true, error: null };
const listeners = new Set<() => void>();
let loadPromise: Promise<void> | null = null;

function setState(next: Partial<OfficerState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function readSavedId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function load(): Promise<void> {
  if (loadPromise) return loadPromise;
  loadPromise = (async () => {
    try {
      const [me, roster] = await Promise.all([
        officerService.current(),
        officerService.list().catch(() => [] as OfficerProfile[]),
      ]);
      const list = roster.length ? roster : [me];
      const savedId = readSavedId();
      const current = list.find((o) => o.officerId === savedId) ?? list.find((o) => o.officerId === me.officerId) ?? me;
      setState({ current, roster: list, loading: false, error: null });
    } catch (e: unknown) {
      setState({
        loading: false,
        error: e instanceof Error ? e.message : 'Could not load the officer profile',
      });
    }
  })();
  return loadPromise;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  void load();
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): OfficerState {
  return state;
}

/** Full store state — used by the Profile page for its loading/error handling. */
export function useOfficerState(): OfficerState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

/** The active officer, or null while it loads. */
export function useCurrentOfficer(): OfficerProfile | null {
  return useOfficerState().current;
}

/** Makes `officer` the active officer everywhere in the app. */
export function setCurrentOfficer(officer: OfficerProfile) {
  if (officer.officerId === state.current?.officerId) return;
  try {
    localStorage.setItem(STORAGE_KEY, officer.officerId);
  } catch {
    /* Selection simply won't persist if storage is unavailable. */
  }
  setState({ current: officer });
}

/** Re-fetches the roster (used by the Profile page's retry action). */
export function refreshOfficers() {
  loadPromise = null;
  setState({ loading: true, error: null });
  void load();
}
