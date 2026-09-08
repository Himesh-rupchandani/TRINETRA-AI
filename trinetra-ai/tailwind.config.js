/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      spacing: {
        '7.5': '1.875rem',
        '8.5': '2.125rem',
        '4.5': '1.125rem',
      },
      fontFamily: {
        sans: ['Inter', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        surface: {
          0: 'rgb(var(--surface-0) / <alpha-value>)',
          1: 'rgb(var(--surface-1) / <alpha-value>)',
          2: 'rgb(var(--surface-2) / <alpha-value>)',
          3: 'rgb(var(--surface-3) / <alpha-value>)',
        },
        line: 'rgb(var(--line) / <alpha-value>)',
        'line-strong': 'rgb(var(--line-strong) / <alpha-value>)',
        ink: {
          DEFAULT: 'rgb(var(--ink) / <alpha-value>)',
          muted: 'rgb(var(--ink-muted) / <alpha-value>)',
          faint: 'rgb(var(--ink-faint) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          strong: 'rgb(var(--accent-strong) / <alpha-value>)',
          weak: 'rgb(var(--accent-weak) / <alpha-value>)',
        },
        // Status — verified contrast on white
        online: 'rgb(var(--status-online) / <alpha-value>)',
        offline: 'rgb(var(--status-offline) / <alpha-value>)',
        'warn': 'rgb(var(--status-warn) / <alpha-value>)',
        'info': 'rgb(var(--status-info) / <alpha-value>)',
        processing: 'rgb(var(--status-processing) / <alpha-value>)',
        // Severity (chips/text on tints)
        critical: 'rgb(var(--sev-critical) / <alpha-value>)',
        high: 'rgb(var(--sev-high) / <alpha-value>)',
        medium: 'rgb(var(--sev-medium) / <alpha-value>)',
        low: 'rgb(var(--sev-low) / <alpha-value>)',
      },
      fontSize: {
        '2xs': ['0.8125rem', { lineHeight: '1.15rem' }],
        xs: ['0.8125rem', { lineHeight: '1.25rem' }],
        sm: ['0.875rem', { lineHeight: '1.45rem' }],
        base: ['0.9375rem', { lineHeight: '1.5rem' }],
      },
      // Shadows are reserved for floating layers only (menus, modals,
      // popovers, toasts). Panels are flat; borders carry structure.
      boxShadow: {
        sm: '0 1px 3px rgb(28 28 26 / 0.08), 0 1px 2px rgb(28 28 26 / 0.04)',
        md: '0 6px 16px -4px rgb(28 28 26 / 0.12), 0 2px 6px -2px rgb(28 28 26 / 0.06)',
        lg: '0 16px 40px -12px rgb(28 28 26 / 0.20)',
      },
    },
  },
  plugins: [],
};
