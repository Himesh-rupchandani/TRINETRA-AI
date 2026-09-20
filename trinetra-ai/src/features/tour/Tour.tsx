import { useEffect, useRef, useState, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Shield, X, CheckCircle2 } from 'lucide-react';
import { TOUR_STEPS } from './tourSteps';
import { tourStore, useTour } from './tourStore';
import { cn } from '@/lib/utils';

interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

const CARD_W = 390;
const CARD_H_EST = 240;
const GAP = 16;
const PAD = 8;

export function Tour() {
  const { open, i } = useTour();
  const step = TOUR_STEPS[i];
  const total = TOUR_STEPS.length;
  const navigate = useNavigate();
  const location = useLocation();
  const [rect, setRect] = useState<Rect | null>(null);
  const [ready, setReady] = useState(false);
  const firedActions = useRef<Set<string>>(new Set());
  const nextBtnRef = useRef<HTMLButtonElement>(null);

  const handleFinish = useCallback(() => {
    tourStore.stop();
    if (location.pathname !== '/') {
      navigate('/');
    }
    // Return smoothly to the top of homepage
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [location.pathname, navigate]);

  useEffect(() => {
    if (open && i === 0) {
      firedActions.current.clear();
      setReady(false);
      setRect(null);
    }
  }, [open, i]);

  useEffect(() => {
    if (!open || !step?.route) return;
    if (location.pathname !== step.route) navigate(step.route);
  }, [open, step, location.pathname, navigate]);

  useEffect(() => {
    if (!open || !step) return;
    const fire = () => {
      if (step.action && !firedActions.current.has(step.id)) {
        firedActions.current.add(step.id);
        window.setTimeout(step.action, 80);
      }
    };
    if (!step.target) {
      if (i === 0) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
      setRect(null);
      setReady(true);
      fire();
      return;
    }
    const target = step.target;
    let stopped = false;
    let tries = 0;
    let timer = 0;
    let hasScrolled = false;
    let stableFrames = 0;
    let lastY = -999999;
    let lastX = -999999;
    const startTime = Date.now();

    const measure = (el: Element): boolean => {
      const r = el.getBoundingClientRect();
      if (r.width < 10 || r.height < 10) return false;
      setRect({ x: r.x, y: r.y, w: r.width, h: r.height });
      return true;
    };
    setReady(false);

    const tick = () => {
      if (stopped) return;
      const el = document.querySelector(target) as HTMLElement | null;
      if (el) {
        if (!hasScrolled) {
          hasScrolled = true;
          try {
            el.scrollIntoView({
              behavior: 'smooth',
              block: 'center',
              inline: 'nearest',
            });
          } catch {
            el.scrollIntoView(true);
          }
        }

        const valid = measure(el);
        if (valid) {
          const r = el.getBoundingClientRect();
          if (Math.abs(r.y - lastY) < 1.5 && Math.abs(r.x - lastX) < 1.5) {
            stableFrames++;
          } else {
            stableFrames = 0;
            lastY = r.y;
            lastX = r.x;
          }

          const elapsed = Date.now() - startTime;
          // Once smooth scrolling settles or after 750ms timeout, show the tour card
          if ((stableFrames >= 5 && elapsed >= 260) || elapsed > 750) {
            setReady(true);
            fire();
            return;
          }
        }
      }

      if (++tries > 160) {
        setRect(null);
        setReady(true);
        fire();
        return;
      }
      timer = window.setTimeout(() => requestAnimationFrame(tick), 35);
    };
    requestAnimationFrame(tick);
    const reflow = () => {
      const el = document.querySelector(target);
      if (el) measure(el);
    };
    window.addEventListener('resize', reflow);
    window.addEventListener('scroll', reflow, true);
    return () => {
      stopped = true;
      clearTimeout(timer);
      window.removeEventListener('resize', reflow);
      window.removeEventListener('scroll', reflow, true);
    };
  }, [open, step, location.pathname, i]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleFinish();
      } else if (e.key === 'Enter' || e.key === 'ArrowRight') {
        e.preventDefault();
        if (i >= total - 1) {
          handleFinish();
        } else {
          tourStore.next(total);
        }
      } else if (e.key === 'ArrowLeft') {
        tourStore.prev();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, total, i, handleFinish]);

  useEffect(() => {
    if (open) nextBtnRef.current?.focus();
  }, [open, i]);

  if (!open || !step) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let cardStyle: React.CSSProperties;
  if (!rect) {
    cardStyle = { left: '50%', top: '50%', transform: 'translate(-50%, -50%)' };
  } else {
    const cardW = Math.min(CARD_W, vw - 24);
    const stickyTop = 135;
    const spaceBelow = vh - (rect.y + rect.h + GAP);
    const spaceAbove = rect.y - GAP - stickyTop;

    let top: number;
    if (spaceBelow >= CARD_H_EST || spaceBelow >= spaceAbove) {
      top = rect.y + rect.h + GAP;
      top = Math.min(top, vh - CARD_H_EST - 12);
    } else {
      top = Math.max(stickyTop + 8, rect.y - GAP - CARD_H_EST);
    }
    const left = Math.max(12, Math.min(rect.x + rect.w / 2 - cardW / 2, vw - cardW - 12));
    cardStyle = { left, top };
  }

  const progress = Math.round(((i + 1) / total) * 100);

  return (
    <>
      {/* Backdrop with smooth fade and subtle blur */}
      <div
        className="fixed inset-0 z-[10040] cursor-pointer bg-slate-950/70 backdrop-blur-[2px] transition-opacity duration-300 ease-out"
        onClick={() => {
          if (i >= total - 1) {
            handleFinish();
          } else {
            tourStore.next(total);
          }
        }}
        aria-hidden
      />

      {/* Surveillance Spotlight Cutout with Command Center HUD brackets */}
      {rect ? (
        <div
          aria-hidden
          className="pointer-events-none fixed z-[10041] rounded-2xl transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={{
            left: rect.x - PAD,
            top: rect.y - PAD,
            width: rect.w + PAD * 2,
            height: rect.h + PAD * 2,
            boxShadow:
              '0 0 0 9999px rgba(15,23,42,0.72), 0 0 0 2px rgba(59,130,246,0.9), 0 0 24px 3px rgba(37,99,235,0.35), 0 12px 36px rgba(0,0,0,0.45)',
          }}
        >
          {/* High-tech Surveillance HUD Corner Brackets */}
          <span className="pointer-events-none absolute -left-1 -top-1 h-3.5 w-3.5 rounded-tl border-l-2 border-t-2 border-blue-400" />
          <span className="pointer-events-none absolute -right-1 -top-1 h-3.5 w-3.5 rounded-tr border-r-2 border-t-2 border-blue-400" />
          <span className="pointer-events-none absolute -bottom-1 -left-1 h-3.5 w-3.5 rounded-bl border-b-2 border-l-2 border-blue-400" />
          <span className="pointer-events-none absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-br border-b-2 border-r-2 border-blue-400" />

          {/* Active Target Radar Pulse Beacon */}
          <span className="pointer-events-none absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex h-3.5 w-3.5 rounded-full bg-blue-600 shadow-sm ring-2 ring-white" />
          </span>
        </div>
      ) : null}

      {/* Tour Step Card with spring physics and elevation */}
      <div
        role="dialog"
        aria-label={`Guided walkthrough step ${i + 1} of ${total}: ${step.title}`}
        className={cn(
          'fixed z-[10042] w-[390px] max-w-[calc(100vw-24px)] overflow-hidden rounded-2xl border border-slate-200/90 bg-white/95 shadow-[0_25px_65px_-12px_rgba(15,23,42,0.32),0_0_0_1px_rgba(15,23,42,0.06)] backdrop-blur-md transition-all duration-400 ease-[cubic-bezier(0.16,1,0.3,1)]',
          !ready ? 'pointer-events-none translate-y-3 scale-[0.97] opacity-0' : 'translate-y-0 scale-100 opacity-100',
        )}
        style={cardStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Animated Gradient Progress Bar */}
        <div className="relative h-1.5 w-full overflow-hidden bg-slate-100">
          <div
            className="h-full bg-gradient-to-r from-blue-600 via-indigo-500 to-cyan-400 transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="p-4 sm:p-5">
          <div className="mb-3 flex items-center gap-2.5">
            <span
              className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 text-white shadow-sm shadow-blue-500/20"
              aria-hidden
            >
              <Shield size={14} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-blue-700">
                  Step {i + 1} / {total}
                </span>
                <span className="h-1 w-1 rounded-full bg-slate-300" />
                <span className="text-[11px] font-medium text-slate-500">{progress}%</span>
              </div>
            </div>
            <div className="ml-auto flex items-center gap-1.5">
              {TOUR_STEPS.map((s, si) => (
                <span
                  key={s.id}
                  className={cn(
                    'h-1.5 rounded-full transition-all duration-300 ease-out',
                    si === i
                      ? 'w-5 bg-gradient-to-r from-blue-600 to-indigo-600 shadow-sm shadow-blue-500/30'
                      : si < i
                        ? 'w-1.5 bg-blue-400'
                        : 'w-1.5 bg-slate-200',
                  )}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={handleFinish}
              aria-label="Exit walkthrough and return to home"
              title="Exit and return to homepage (Esc)"
              className="grid h-7 w-7 place-items-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
            >
              <X size={14} aria-hidden />
            </button>
          </div>

          <h3 className="text-[15px] font-bold leading-tight tracking-tight text-slate-900">{step.title}</h3>
          <p className="mt-2 text-[13px] leading-[1.55] text-slate-600">{step.body}</p>

          <div className="mt-5 flex items-center gap-2">
            <button
              type="button"
              onClick={() => tourStore.prev()}
              className={cn(
                'inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 shadow-sm transition-all duration-150 hover:bg-slate-50 hover:scale-[1.02] active:scale-[0.98]',
                i === 0 && 'invisible',
              )}
            >
              <ChevronLeft size={13} aria-hidden /> Back
            </button>
            <span className="ml-auto text-[10px] text-slate-400">Esc to exit • ← → keys</span>
            {i === total - 1 ? (
              <button
                ref={nextBtnRef}
                type="button"
                onClick={handleFinish}
                className="inline-flex h-8.5 items-center gap-1.5 rounded-lg bg-gradient-to-r from-emerald-600 to-teal-600 px-4 text-xs font-bold text-white shadow-md shadow-emerald-600/25 transition-all duration-200 hover:from-emerald-700 hover:to-teal-700 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                <CheckCircle2 size={14} aria-hidden /> Finish Tour
              </button>
            ) : (
              <button
                ref={nextBtnRef}
                type="button"
                onClick={() => tourStore.next(total)}
                className="inline-flex h-8.5 items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 text-xs font-bold text-white shadow-md shadow-blue-600/25 transition-all duration-200 hover:from-blue-700 hover:to-indigo-700 hover:shadow-lg hover:scale-[1.02] active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2"
              >
                {step.cta ?? 'Next'}
                <ChevronRight size={14} aria-hidden />
              </button>
            )}
          </div>
        </div>

        <div className="border-t border-slate-100 bg-slate-50/80 px-4 py-2.5">
          <p className="text-[10px] font-medium text-slate-500">
            TRINETRA AI — Gujarat Police • Command Center Walkthrough
          </p>
        </div>
      </div>
    </>
  );
}
