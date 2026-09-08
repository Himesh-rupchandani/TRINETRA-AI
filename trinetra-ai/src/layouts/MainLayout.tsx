import { Outlet } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { TopNav } from '@/components/layout/TopNav';
import { AlertBanner } from '@/components/layout/AlertBanner';

/**
 * Control-room shell: header on top, full module navigation bar below it,
 * then the alert banner and the active page. No side drawer — every module
 * stays visible in the top bar on all screen sizes.
 */
export function MainLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-surface-0">
      <Header />
      <TopNav />
      <AlertBanner />
      <main id="main" className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  );
}
