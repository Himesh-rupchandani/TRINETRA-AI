import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from '@/app/App';
import './index.css';

/**
 * TRINETRA AI runs the "Sentinel Ops" dark command-room theme — a single
 * always-on dark palette (option (a): no light/dark toggle, no half-styled
 * variants). Enforce the dark colour scheme before the first paint and clear
 * any legacy theme state so a refresh or reopen can never re-activate the
 * removed Night/Dark Mode class toggle or a stale OS preference (this also
 * guards fullscreen views).
 */
const rootElement = document.documentElement;
rootElement.classList.remove('dark');
rootElement.style.colorScheme = 'dark';
try {
  localStorage.removeItem('trinetra.theme');
} catch {
  /* storage unavailable — non-fatal */
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
