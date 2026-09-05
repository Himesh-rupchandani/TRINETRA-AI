import type { ReactNode } from 'react';
import { ToastProvider } from '@/features/system/ToastProvider';
import { LiveProvider } from '@/features/alerts/LiveProvider';

/**
 * Application-wide providers.
 * LiveProvider owns the single realtime connection (simulator today,
 * WebSocket/SSE once the backend is live) and the session alert state.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <LiveProvider>{children}</LiveProvider>
    </ToastProvider>
  );
}
