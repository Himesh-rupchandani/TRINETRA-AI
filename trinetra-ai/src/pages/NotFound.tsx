import { Link } from 'react-router-dom';
import { Radar } from 'lucide-react';
import { EyeMark } from '@/components/common/EyeMark';

export default function NotFound() {
  return (
    <div className="relative grid h-full place-items-center overflow-hidden p-8">
      {/* Third-eye rings — the eye is watching, even here */}
      <div className="eye-rings pointer-events-none absolute inset-0 opacity-40" aria-hidden />
      <div className="panel relative max-w-md p-6 text-center sm:p-8">
        <EyeMark size={56} className="mx-auto" />
        <p className="mt-3 font-mono text-2xs font-bold uppercase tracking-[0.3em] text-brand">404 · Signal lost</p>
        <h1 className="mt-1.5 text-sm font-bold text-ink">Route not found</h1>
        <p className="mt-2 text-2xs leading-relaxed text-ink-muted">
          This screen does not exist in the Trinetra control room. Return to the Command Center to
          continue your investigation.
        </p>
        <div className="mt-4 flex items-center justify-center gap-2">
          <Link to="/" className="btn-primary">
            Back to Command Center
          </Link>
          <Link to="/cameras" className="btn-ghost">
            <Radar size={13} aria-hidden /> Camera wall
          </Link>
        </div>
        <p className="mt-5 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
          Sentinel Hackathon · TRINETRA AI
        </p>
      </div>
    </div>
  );
}
