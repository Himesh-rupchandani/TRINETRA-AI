/**
 * Global copyright / credit bar rendered at the bottom of every screen.
 * Kept deliberately self-contained: it only uses the project's own logo asset
 * and design tokens, so adding the notice does not touch any other feature.
 */
export function CopyrightFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="shrink-0 border-t border-line bg-surface-1" aria-label="Copyright and credits">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-center gap-x-2 gap-y-1 px-4 py-2.5 text-center text-2xs text-ink-faint sm:px-5">
        <img
          src="/trinetra-logo-512.png"
          alt="TRINETRA AI logo"
          className="h-6 w-6 shrink-0 rounded-full ring-1 ring-line"
        />
        <span>
          © {year} <span className="font-semibold text-ink-muted">TRINETRA AI</span> · All rights reserved
        </span>
        <span className="text-ink-faint/50" aria-hidden>
          |
        </span>
        <span>
          Created by{' '}
          <span className="font-medium text-ink-muted">Prof. Akshay Ranpariya</span> ·{' '}
          <span className="font-medium text-ink-muted">Ravi Gohel</span> ·{' '}
          <span className="font-medium text-ink-muted">Himesh Rupchandani</span>
        </span>
      </div>
    </footer>
  );
}
