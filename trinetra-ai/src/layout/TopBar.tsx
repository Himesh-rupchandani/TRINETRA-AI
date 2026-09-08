import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Bell, Menu, PanelLeftClose, Search, UserRound } from 'lucide-react';
import { cn, normalisePlate } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { config } from '@/lib/config';
import { useOfficer } from '@/features/officer/OfficerProvider';

const TITLES: [RegExp, string][] = [
  [/^\/?$/, 'Command Center'],
  [/^\/cameras\/[^/]+$/, 'Camera'],
  [/^\/cameras/, 'Live Cameras'],
  [/^\/vehicles\/[^/]+$/, 'Vehicle Investigation'],
  [/^\/vehicles/, 'Find a Vehicle'],
  [/^\/video-analysis/, 'Video Analysis'],
  [/^\/alerts/, 'Alerts'],
  [/^\/events/, 'Vehicle Log'],
  [/^\/gis/, 'City Map'],
  [/^\/registry/, 'Camera Registry'],
  [/^\/watchlist/, 'Wanted List'],
  [/^\/system/, 'System Status'],
  [/^\/profile/, 'Officer Profile'],
];

function pageTitle(pathname: string): string {
  for (const [re, title] of TITLES) if (re.test(pathname)) return title;
  return 'SENTINEL';
}

const CONNECTION: Record<string, { label: string; tone: string }> = {
  LIVE: { label: 'Live', tone: 'text-online' },
  SIMULATED: { label: 'Demo feed', tone: 'text-critical' },
  CONNECTING: { label: 'Connecting', tone: 'text-warn' },
  OFFLINE: { label: 'Offline', tone: 'text-offline' },
};

/** IST operations clock — standard in control rooms. */
function useOpsClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  }).format(now);
}

/**
 * Top bar — page title on the left (so pages stay open and airy),
 * global plate search centred, system status on the right.
 */
export function TopBar({
  onMenu,
  onToggleCollapse,
  showCollapseToggle,
}: {
  onMenu: () => void;
  onToggleCollapse: () => void;
  showCollapseToggle: boolean;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const { counts } = useAlerts();
  const { connection } = useLiveEvents();
  const { current: officer } = useOfficer();
  const [quick, setQuick] = useState('');
  const clock = useOpsClock();

  const conn = CONNECTION[connection] ?? CONNECTION.OFFLINE;

  const submitQuick = (e: React.FormEvent) => {
    e.preventDefault();
    const p = normalisePlate(quick);
    if (p) navigate(`/vehicles/${p}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-surface-1/90 px-4 backdrop-blur-md sm:px-5">
      <button
        type="button"
        className="grid h-9 w-9 place-items-center rounded-lg text-ink-muted transition-all duration-150 hover:bg-surface-2 hover:text-ink active:scale-95 md:hidden"
        onClick={onMenu}
        aria-label="Open navigation"
      >
        <Menu size={17} aria-hidden />
      </button>
      {showCollapseToggle && (
        <button
          type="button"
          className="hidden h-9 w-9 place-items-center rounded-lg text-ink-muted transition-colors duration-150 hover:bg-surface-2 hover:text-ink active:scale-95"
          onClick={onToggleCollapse}
          aria-label="Toggle navigation rail"
        >
          <PanelLeftClose size={16} aria-hidden />
        </button>
      )}

      {/* Page title */}
      <h1 className="min-w-0 truncate text-base font-semibold text-ink">
        {pageTitle(location.pathname)}
      </h1>

      {/* Global plate search */}
      <div className="hidden min-w-0 flex-1 justify-center px-4 md:flex">
        <form onSubmit={submitQuick} className="w-full max-w-md" role="search">
          <label htmlFor="global-plate-search" className="sr-only">
            Trace registration number
          </label>
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
            <input
              id="global-plate-search"
              value={quick}
              onChange={(e) => setQuick(e.target.value.toUpperCase())}
              placeholder="Search a number plate — GJ01AB1234"
              className="field h-9 pl-9 font-mono uppercase"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        </form>
      </div>

      {/* Right cluster */}
      <div className="ml-auto flex items-center gap-1 sm:gap-1.5">
        {config.useMocks && (
          <span className="mr-1 hidden rounded-full border border-line bg-surface-2 px-2 py-0.5 text-[11px] font-semibold text-ink-muted xl:inline">
            Demo data
          </span>
        )}

        <span
          className={cn('mr-1 hidden items-center gap-1.5 text-xs font-semibold sm:inline-flex', conn.tone)}
          title={`Realtime channel: ${connection}`}
        >
          <span className={cn('h-1.5 w-1.5 rounded-full bg-current', connection === 'LIVE' && 'animate-pulse-dot')} aria-hidden />
          {conn.label}
        </span>

        <span
          className="mono mr-1 hidden items-center rounded-md border border-line bg-surface-1 px-2 py-1 text-xs tabular-nums text-ink-muted lg:inline-flex"
          title="Operations clock — Indian Standard Time"
        >
          {clock}
          <span className="ml-1.5 text-[9.5px] font-semibold text-ink-faint">IST</span>
        </span>

        <Link
          to="/alerts"
          className="relative grid h-9 w-9 place-items-center rounded-lg text-ink-muted transition-all duration-150 hover:bg-surface-2 hover:text-ink active:scale-95"
          aria-label={`${counts.ACTIVE} active alerts — open Alerts`}
        >
          <Bell size={16} aria-hidden />
          {counts.ACTIVE > 0 && (
            <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-critical ring-2 ring-surface-1" aria-hidden />
          )}
        </Link>

        <Link
          to="/profile"
          className="hidden items-center gap-2.5 rounded-lg py-1 pl-3 pr-1 transition-all duration-150 hover:bg-surface-2 active:scale-[0.98] xl:flex"
          aria-label="Open officer profile"
        >
          <span className="min-w-0 text-right">
            <span className="block max-w-[150px] truncate text-xs font-semibold leading-tight text-ink">
              {officer?.name ?? 'System Operator'}
            </span>
            <span className="block text-[10.5px] leading-tight text-ink-faint">
              {officer?.designation ?? 'Control Center'}
            </span>
          </span>
          {officer ? (
            <img src={officer.photoUrl} alt="" className="h-8 w-8 shrink-0 rounded-full object-cover" aria-hidden />
          ) : (
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-3 text-ink-muted" aria-hidden>
              <UserRound size={14} />
            </span>
          )}
        </Link>
      </div>
    </header>
  );
}
