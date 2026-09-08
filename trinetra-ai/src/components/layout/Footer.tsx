/** Slim closing strip: product name on the left, team credit on the right. */
export function Footer() {
  return (
    <footer className="shrink-0 border-t border-line bg-surface-1">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-1 px-4 py-3 text-2xs text-ink-faint sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <p>
          <span className="font-bold text-ink-muted">TRINETRA AI</span> — Intelligent Vision.
          Faster Response.
        </p>
        <p>Built by Team Trinetra · Gujarat Police Innovation Hackathon</p>
      </div>
    </footer>
  );
}
