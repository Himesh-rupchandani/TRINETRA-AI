import { Outlet, useLocation } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { TopNav } from '@/components/layout/TopNav';
import { HeroBanner } from '@/components/layout/HeroBanner';
import { AlertBanner } from '@/components/layout/AlertBanner';
import { Footer } from '@/components/layout/Footer';

/**
 * Control-room shell: header on top, alert banner, hero card on the home
 * page, then the workflow menu bar, the active page and a slim footer.
 * The page content softly fades in on every navigation.
 */
export function MainLayout() {
  const location = useLocation();
  const isHome = location.pathname === '/';

  return (
    <div className="flex min-h-screen flex-col bg-surface-0">
      <Header />
      <AlertBanner />
      {isHome && <HeroBanner />}
      <TopNav />
      <main key={location.pathname} id="main" className="fade-in min-h-0 flex-1">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
