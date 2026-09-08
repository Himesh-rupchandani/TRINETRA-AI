import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';
import { AlertTicker } from './AlertTicker';
import { useLocalStorage, useMediaQuery } from '@/hooks/useUi';
import { cn } from '@/lib/utils';

/**
 * SENTINEL application shell — persistent side navigation + top bar +
 * realtime alert ticker, content constrained to a readable measure.
 */
export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useLocalStorage('trinetra.sidebarCollapsed', false);
  const isDesktop = useMediaQuery('(min-width: 1024px)');
  const effectiveCollapsed = isDesktop ? collapsed : false;

  return (
    <div className="flex h-full min-h-screen bg-surface-0">
      <SideNav open={mobileOpen} onClose={() => setMobileOpen(false)} collapsed={effectiveCollapsed} />
      <div
        className={cn(
          'flex min-w-0 flex-1 flex-col transition-[padding] duration-200',
          effectiveCollapsed ? 'lg:pl-[68px]' : 'lg:pl-[248px]',
        )}
      >
        <TopBar
          onMenu={() => setMobileOpen(true)}
          onToggleCollapse={() => setCollapsed(!collapsed)}
          collapsed={effectiveCollapsed}
        />
        <AlertTicker />
        <main id="main" className="min-h-0 flex-1">
          <div className="mx-auto h-full w-full max-w-[1600px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
