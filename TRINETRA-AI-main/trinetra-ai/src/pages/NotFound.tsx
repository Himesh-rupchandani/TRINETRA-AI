import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';

export default function NotFound() {
  return (
    <div className="grid h-full place-items-center p-8">
      <div className="panel max-w-md p-6 sm:p-8 text-center">
        <Compass size={26} className="mx-auto mb-3 text-ink-faint" aria-hidden />
        <h1 className="text-sm font-bold text-ink">Route not found</h1>
        <p className="mt-2 text-2xs leading-relaxed text-ink-muted">
          This screen does not exist in the Trinetra control room. Return to the Command Center to continue
          your investigation.
        </p>
        <Link to="/" className="btn-primary mt-4">
          Back to Command Center
        </Link>
      </div>
    </div>
  );
}
