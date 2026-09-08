import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { SideNav } from './SideNav';
import { TopBar } from './TopBar';
import { AlertTicker } from './AlertTicker';
import { useLocalStorage, useMediaQuery } from '@/hooks/useUi';
import { cn } from '@/lib/utils';

/**
 * SENTINEL application shell — persistent left navigation (full at
 * ≥1200px, icon rail at 768–1199px, drawer below 768px), slim top bar,
 * realtime alert ticker. Content constrained to a 1440px measure.
 */
export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userCollapsed, setUserCollapsed] = useLocalStorage('trinetra.sidebarCollapsed', false);
  const isWide = useMediaQuery('(min-width: 1200px)');
  const isTablet = useMediaQuery('(min-width: 768px)');

  // ≥1200px: full rail unless the operator collapsed it. 768–1199px:
  // icon-only rail. <768px: off-canvas drawer (rail always expanded).
  const collapsed = isWide ? userCollapsed : isTablet ? true : false;

  return (
    <div className="flex h-full min-h-screen bg-surface-0">
      <SideNav open={mobileOpen} onClose={() => setMobileOpen(false)} collapsed={isTablet ? collapsed : false} />
      <div
        className={cn(
          'flex min-w-0 flex-1 flex-col transition-[padding] duration-200',
          isTablet && (collapsed ? 'md:pl-[64px]' : 'md:pl-[232px]'),
        )}
      >
        <TopBar
          onMenu={() => setMobileOpen(true)}
          onToggleCollapse={() => setUserCollapsed(!userCollapsed)}
          showCollapseToggle={isWide}
        />
        <AlertTicker />
        <main id="main" className="min-h-0 flex-1">
          <div className="mx-auto h-full w-full max-w-[1440px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
