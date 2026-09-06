import { createContext, useContext, useEffect, type ReactNode } from 'react';

/**
 * Night Mode / Dark Mode has been removed. The application is permanently
 * Light Mode, so the theme is a fixed `'light'` value and there is no toggle.
 * The `dark` class and any previously persisted theme are cleared on mount so
 * a refresh or reopen can never re-activate Dark Mode.
 */
interface ThemeContextValue {
  theme: 'light';
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('dark');
    root.style.colorScheme = 'light';
    try {
      localStorage.removeItem('trinetra.theme');
    } catch {
      /* storage unavailable — non-fatal */
    }
  }, []);

  return <ThemeContext.Provider value={{ theme: 'light' }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
