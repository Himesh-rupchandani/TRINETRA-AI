import { useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Bell,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  UserRound,
} from 'lucide-react';
import { cn, normalisePlate } from '@/lib/utils';
import { useAlerts } from '@/hooks/useAlerts';
import { useLiveEvents } from '@/hooks/useLiveEvents';
import { config } from '@/lib/config';
import { useOfficer } from '@/features/officer/OfficerProvider';

const CONNECTION_TONE: Record<string, string> = {
  LIVE: 'text-online',
  SIMULATED: 'text-critical',
  CONNECTING: 'text-degraded',
  OFFLINE: 'text-offline',
};

/** Operations clock — control rooms always run on a visible wallclock (IST). */
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

export function Header({
  onMenu,
  onToggleCollapse,
  collapsed,
}: {
  onMenu: () => void;
  onToggleCollapse: () => void;
  collapsed: boolean;
}) {
  const navigate = useNavigate();
  const { counts } = useAlerts();
  const { connection } = useLiveEvents();
  const { current: officer } = useOfficer();
  const [quick, setQuick] = useState('');
  const clock = useOpsClock();

  const submitQuick = (e: React.FormEvent) => {
    e.preventDefault();
    const p = normalisePlate(quick);
    if (p) navigate(`/vehicles/${p}`);
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2.5 border-b border-line bg-surface-1/85 px-3.5 backdrop-blur-md sm:gap-3 sm:px-5">
      <button type="button" className="btn-ghost h-9 w-9 px-0 lg:hidden" onClick={onMenu} aria-label="Open navigation">
        <Menu size={16} aria-hidden />
      </button>
      <button
        type="button"
        className="btn-ghost hidden h-9 w-9 px-0 lg:inline-flex"
        onClick={onToggleCollapse}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <PanelLeftOpen size={16} aria-hidden /> : <PanelLeftClose size={16} aria-hidden />}
      </button>

      <div className="min-w-0 lg:hidden">
        <p className="truncate text-sm font-black leading-tight tracking-[0.08em] text-ink">{config.productName}</p>
        <p className="hidden truncate text-2xs leading-tight text-ink-faint sm:block">{config.appName} · Control Room</p>
      </div>

      {/* Global plate search — the hero entry point, reachable from every screen */}
      <form onSubmit={submitQuick} className="hidden max-w-md flex-1 md:block" role="search">
        <label htmlFor="global-plate-search" className="sr-only">
          Trace registration number
        </label>
        <div className="relative">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" aria-hidden />
          <input
            id="global-plate-search"
            value={quick}
            onChange={(e) => setQuick(e.target.value.toUpperCase())}
            placeholder="Search number plate, camera, or location…"
            className="input h-10 pl-9 font-mono uppercase"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      </form>

      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        {/* Operations clock — IST wallclock, standard in control rooms */}
        <span
          className="hidden items-center gap-1.5 rounded-md border border-line bg-surface-2/70 px-2 py-1 font-mono text-2xs tabular-nums text-ink-muted md:inline-flex"
          title="Operations clock — Indian Standard Time"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-brand" aria-hidden />
          {clock} <span className="font-semibold text-ink-faint">IST</span>
        </span>

        {config.useMocks && (
          <span className="chip hidden border-brand/25 bg-brand/10 font-semibold text-brand xl:inline-flex">
            Demo Data
          </span>
        )}

        <span
          className={cn(
            'hidden items-center gap-1.5 text-2xs font-bold uppercase tracking-wide sm:inline-flex',
            CONNECTION_TONE[connection],
          )}
          title={`Realtime channel: ${connection}`}
        >
          <span className={cn('h-2 w-2 rounded-full bg-current', connection === 'LIVE' && 'animate-pulse')} aria-hidden />
          {connection === 'SIMULATED'
            ? 'Demo Feed'
            : connection === 'LIVE'
              ? 'Live Feed'
              : connection === 'CONNECTING'
                ? 'Connecting'
                : 'Offline'}
        </span>

        <button
          type="button"
          onClick={() => navigate('/alerts')}
          className="relative grid h-9 w-9 place-items-center rounded-lg border border-line text-ink-muted transition-colors hover:bg-surface-2 hover:text-ink"
          aria-label={`${counts.ACTIVE} alerts need your attention — open Alerts`}
        >
          <Bell size={16} className={counts.ACTIVE > 0 ? 'animate-pulse text-critical' : ''} aria-hidden />
          {counts.ACTIVE > 0 && (
            <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-critical px-1 font-mono text-[10px] font-bold text-white">
              {counts.ACTIVE}
            </span>
          )}
        </button>

        <button
          type="button"
          onClick={() => navigate('/profile')}
          className="hidden items-center gap-2.5 border-l border-line pl-3 text-left xl:flex"
          aria-label="Open officer profile"
        >
          {officer ? (
            <img
              src={officer.photoUrl}
              alt=""
              className="h-8 w-8 shrink-0 rounded-full object-cover ring-1 ring-line"
              aria-hidden
            />
          ) : (
            <span className="grid h-8 w-8 place-items-center rounded-full bg-brand/10 text-brand" aria-hidden>
              <UserRound size={15} />
            </span>
          )}
          <div className="leading-tight">
            <p className="max-w-[160px] truncate text-xs font-semibold text-ink">{officer?.name ?? 'System Operator'}</p>
            <p className="text-2xs text-ink-faint">{officer?.designation ?? 'Control Center'}</p>
          </div>
        </button>
      </div>
    </header>
  );
}
