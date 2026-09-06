import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from '@/app/App';
import './index.css';

/**
 * TRINETRA AI is permanently Light Mode — Night/Dark Mode has been removed.
 * Enforce that before the first paint and clear any legacy dark-mode state so
 * a refresh or reopen can never re-activate Dark Mode, regardless of the OS or
 * browser color scheme (this also guards fullscreen views).
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
