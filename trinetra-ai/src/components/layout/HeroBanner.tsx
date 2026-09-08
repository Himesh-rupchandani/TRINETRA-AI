import { useNavigate } from 'react-router-dom';
import { Bell, Cctv, Play, Video } from 'lucide-react';
import { useCameras } from '@/hooks/useCameras';
import { useAlerts } from '@/hooks/useAlerts';

/**
 * Wide hero card between the title bar and the menu bar (home page only):
 * night-city CCTV backdrop, headline, two workflow entry buttons, live
 * network stats and the TRINETRA quote panel on the right.
 */
export function HeroBanner() {
  const navigate = useNavigate();
  const { stats } = useCameras();
  const { active } = useAlerts();

  return (
    <section aria-label="TRINETRA AI overview" className="relative shrink-0 overflow-hidden bg-slate-950 text-white">
      <img
        src="/cctv/cctv-01.jpg"
        alt=""
        aria-hidden
        className="absolute inset-0 h-full w-full object-cover opacity-45"
      />
      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-r from-slate-950 via-slate-950/80 to-slate-950/25"
      />

      <div className="relative mx-auto flex max-w-[1600px] flex-col gap-5 px-4 py-8 sm:px-5 lg:flex-row lg:items-center lg:justify-between lg:py-10">
        <div className="max-w-xl">
          <p className="text-2xs font-bold uppercase tracking-[0.2em] text-blue-300">
            CCTV Intelligence · Control Room
          </p>
          <h1 className="mt-2 text-3xl font-extrabold leading-tight tracking-tight sm:text-4xl">
            Safer Streets,
            <br />
            <span className="text-blue-400">Smarter Response</span>
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-300">
            AI-powered vehicle detection, number-plate recognition and live CCTV
            monitoring — helping officers find any vehicle in seconds.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => navigate('/cameras')}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-semibold text-white shadow-lg transition-colors hover:bg-blue-500"
            >
              <Play size={15} aria-hidden /> View Live Cameras
            </button>
            <button
              type="button"
              onClick={() => navigate('/video-analysis')}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/30 bg-white/5 px-5 text-sm font-semibold text-white backdrop-blur-sm transition-colors hover:bg-white/15"
            >
              <Video size={15} aria-hidden /> Analyse a Video
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {stats.total > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-2xs font-semibold text-white backdrop-blur-sm">
                <Cctv size={13} className="text-emerald-300" aria-hidden />
                {stats.online}/{stats.total} cameras online
              </span>
            )}
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-2xs font-semibold text-white backdrop-blur-sm">
              <Bell size={13} className={active.length ? 'text-rose-300' : 'text-slate-300'} aria-hidden />
              {active.length} active alert{active.length === 1 ? '' : 's'}
            </span>
          </div>
        </div>

        <figure className="hidden w-64 shrink-0 rounded-xl border border-white/15 bg-white/5 p-5 backdrop-blur-sm lg:block">
          <Cctv size={22} className="text-blue-300" aria-hidden />
          <blockquote className="mt-3 text-lg font-medium italic leading-snug text-white">
            “Technology for a Safer Tomorrow”
          </blockquote>
          <figcaption className="mt-3 text-2xs font-bold uppercase tracking-[0.18em] text-slate-400">
            — TRINETRA AI
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
