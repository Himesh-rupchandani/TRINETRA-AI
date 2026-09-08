import type { ReactNode } from 'react';
import { ToastProvider } from '@/features/system/ToastProvider';
import { LiveProvider } from '@/features/alerts/LiveProvider';
import { OfficerProvider } from '@/features/officer/OfficerProvider';

/**
 * Application-wide providers.
 * LiveProvider owns the single realtime connection (simulator today,
 * WebSocket/SSE once the backend is live) and the session alert state.
 *
 * There is no ThemeProvider: the app runs the dark command-center theme
 * permanently (enforced pre-render in main.tsx).
 */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <LiveProvider>
        <OfficerProvider>{children}</OfficerProvider>
      </LiveProvider>
    </ToastProvider>
  );
}
