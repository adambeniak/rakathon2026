import type { Config } from 'tailwindcss'

// Colours read RGB channels from src/index.css so opacity modifiers (`bg-card/95`) work.
const c = (name: string) => `rgb(var(--rgb-${name}) / <alpha-value>)`
const sans = ['"IBM Plex Sans"', '"Segoe UI"', 'system-ui', 'sans-serif']

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: c('surface'),
        card: c('card'),
        sunken: c('sunken'),
        ink: c('ink'),
        muted: c('muted'),
        hairline: c('hairline'),
        'line-strong': c('line-strong'),
        accent: {
          DEFAULT: c('accent'),
          hover: c('accent-hover'),
          soft: c('accent-soft'),
          on: c('on-accent'),
        },
        missing: { DEFAULT: c('missing'), bg: c('missing-bg') },
        conflict: { DEFAULT: c('conflict'), bg: c('conflict-bg') },
        stale: { DEFAULT: c('stale'), bg: c('stale-bg') },
        verified: { DEFAULT: c('verified'), bg: c('verified-bg') },
        ai: { DEFAULT: c('ai'), bg: c('ai-bg') },
      },
      fontFamily: {
        sans,
        // Headings are IBM Plex Sans 600 now; `font-serif` in features follows the sans stack.
        serif: sans,
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'Menlo', 'monospace'],
      },
      // rem only, 14px floor: the "A+ Větší písmo" switch scales the root font size.
      fontSize: {
        xs: ['0.875rem', { lineHeight: '1.25rem' }],
        sm: ['0.9375rem', { lineHeight: '1.375rem' }],
        base: ['1.0625rem', { lineHeight: '1.625rem' }],
        lg: ['1.25rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.625rem', { lineHeight: '2.125rem' }],
        '3xl': ['2.25rem', { lineHeight: '2.75rem', letterSpacing: '-0.015em' }],
      },
      borderRadius: { sm: '6px', DEFAULT: '6px', md: '8px', lg: '12px' },
      boxShadow: { pop: 'var(--shadow-pop)' },
      maxWidth: { page: '1240px' },
    },
  },
  plugins: [],
} satisfies Config
