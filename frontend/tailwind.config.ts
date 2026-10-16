import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: 'var(--surface)',
        card: 'var(--card)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        hairline: 'var(--hairline)',
        accent: { DEFAULT: 'var(--accent)', hover: 'var(--accent-hover)', soft: 'var(--accent-soft)' },
        missing: { DEFAULT: 'var(--missing)', bg: 'var(--missing-bg)' },
        conflict: { DEFAULT: 'var(--conflict)', bg: 'var(--conflict-bg)' },
        stale: { DEFAULT: 'var(--stale)', bg: 'var(--stale-bg)' },
        verified: { DEFAULT: 'var(--verified)', bg: 'var(--verified-bg)' },
        ai: { DEFAULT: 'var(--ai)', bg: 'var(--ai-bg)' },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        serif: ['"Source Serif 4 Variable"', 'Georgia', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: { xs: '12px', sm: '14px', base: '16px', xl: '20px', '2xl': '24px', '3xl': '32px' },
      borderRadius: { DEFAULT: '6px', lg: '10px' },
    },
  },
  plugins: [],
} satisfies Config
