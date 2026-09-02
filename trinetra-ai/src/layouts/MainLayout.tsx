import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { AlertBanner } from '@/components/layout/AlertBanner';
import { useLocalStorage, useMediaQuery } from '@/hooks/useUi';
import { cn } from '@/lib/utils';

/** Standard control-room shell: persistent sidebar + header + alert banner. */
export function MainLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useLocalStorage('trinetra.sidebarCollapsed', false);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const effectiveCollapsed = isDesktop ? collapsed : false;

  return (
    <div className="flex h-full min-h-screen bg-surface-0">
      <Sidebar open={mobileOpen} onClose={() => setMobileOpen(false)} collapsed={effectiveCollapsed} />
      <div
        className={cn(
          'flex min-w-0 flex-1 flex-col transition-[padding] duration-200',
          effectiveCollapsed ? 'lg:pl-[72px]' : 'lg:pl-[240px]',
        )}
      >
        <Header
          onMenu={() => setMobileOpen(true)}
          onToggleCollapse={() => setCollapsed(!collapsed)}
          collapsed={effectiveCollapsed}
        />
        <AlertBanner />
        <main id="main" className="min-h-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
