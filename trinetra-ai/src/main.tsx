import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from '@/app/App';
import './index.css';

/**
 * TRINETRA AI · SENTINEL runs the light (white) theme permanently.
 * Enforce it before the first paint and clear any legacy theme state so a
 * refresh or reopen can never re-activate another scheme, regardless of the
 * OS or browser color scheme (this also guards fullscreen views).
 */
const rootElement = document.documentElement;
rootElement.classList.remove('dark');
rootElement.style.colorScheme = 'light';
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
