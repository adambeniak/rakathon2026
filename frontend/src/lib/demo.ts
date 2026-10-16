import type { Role } from './domain'

// Simulated "today" and role for the demo. Module-level so the API layer can read it;
// DemoContext keeps React in sync and persists it.
export const DEMO_DATES = ['2026-10-02', '2026-10-12', '2026-10-16', '2026-10-19', '2026-10-21', '2026-10-22'] as const

const KEY = 'stafeta.demo'
let state: { role: Role; today: string } = { role: 'coordinator', today: '2026-10-16' }

try {
  const raw = localStorage.getItem(KEY)
  if (raw) state = { ...state, ...(JSON.parse(raw) as Partial<typeof state>) }
} catch {
  /* storage unavailable: keep defaults */
}

export function getDemo(): { role: Role; today: string } {
  return state
}

export function setDemo(next: { role: Role; today: string }): void {
  state = next
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    /* ignore */
  }
}
