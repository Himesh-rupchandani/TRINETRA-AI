import type { ReactNode } from 'react';
import { ToastProvider } from '@/features/system/ToastProvider';
import { LiveProvider } from '@/features/alerts/LiveProvider';
import { OfficerProvider } from '@/features/officer/OfficerProvider';
import { useGlobalIconFx } from '@/features/system/useIconFx';

/**
 * Application-wide providers.
 * LiveProvider owns the single realtime connection (simulator today,
 * WebSocket/SSE once the backend is live) and the session alert state.
 *
 * There is no ThemeProvider: Night/Dark Mode was removed and the app is
 * permanently Light Mode (enforced pre-render in main.tsx).
 */
export function AppProviders({ children }: { children: ReactNode }) {
  useGlobalIconFx();
  return (
    <ToastProvider>
      <LiveProvider>
        <OfficerProvider>{children}</OfficerProvider>
      </LiveProvider>
    </ToastProvider>
  );
}
