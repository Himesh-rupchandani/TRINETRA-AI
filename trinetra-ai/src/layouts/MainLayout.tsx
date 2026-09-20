import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { TopNav } from '@/components/layout/TopNav';
import { HeroBanner } from '@/components/layout/HeroBanner';
import { AlertBanner } from '@/components/layout/AlertBanner';
import { BackendCheck } from '@/components/layout/BackendCheck';
import { LiveAlertToaster } from '@/features/alerts/LiveAlertToaster';
import { LivePlateToaster } from '@/features/alerts/LivePlateToaster';
import { Tour } from '@/features/tour/Tour';
import { tourStore } from '@/features/tour/tourStore';

/**
 * Control-room shell: header on top, alert banner, hero card on the home
 * page, then the workflow menu bar and the active page.
 */
export function MainLayout() {
  const location = useLocation();
  const isHome = location.pathname === '/';

  // Guided walkthrough: greets a first-time visitor once (judges!), then
  // never nags again — the ✨ Tour header button replays it on demand.
  useEffect(() => {
    let seen = false;
    try {
      seen = localStorage.getItem('trinetra-tour') === 'seen';
    } catch {
      /* private mode: skip auto-open to be safe */
      seen = true;
    }
    if (seen || location.pathname !== '/') return;
    const t = window.setTimeout(() => tourStore.start(), 1600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-surface-0">
      <Header />
      {/* Deployment self-diagnosis: renders only when this origin cannot serve
          the API (or seeded it badly), so `0/0` and `0/1` always come with a
          reason. See lib/backendStatus.ts. */}
      <BackendCheck />
      {isHome && <AlertBanner />}
      {isHome && <HeroBanner />}
      <TopNav />
      <main id="main" className="min-h-0 flex-1">
        <Outlet />
      </main>
      <LiveAlertToaster />
      <LivePlateToaster />
      <Tour />
    </div>
  );
}
