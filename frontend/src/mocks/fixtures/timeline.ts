// MOCK copy – replaced by API in F2/F3
import type { TimelineEvent } from '@/lib/domain'
import { golden } from './golden'

export function timelineAt(today: string): TimelineEvent[] {
  const events: TimelineEvent[] = golden.timeline.map((e) => ({
    date: e.date,
    label: e.event,
    note: e.precision === 'month-half' ? 'přibližné datum' : undefined,
  }))
  events.push(
    { date: '2026-10-26', label: 'Algeziologie – po MDT', note: 'po MDT, nezahrnuto do handoveru', excluded: true },
    { date: '2026-10-27', label: 'Psychologie KOC 2 – po MDT', note: 'po MDT, nezahrnuto do handoveru', excluded: true },
  )
  // The planned oncology consult (4. 11.) is shown as a plan; everything after "today" is hidden except plans.
  return events
    .filter((e) => e.excluded || e.date <= today || e.label.includes('(plán)'))
    .sort((a, b) => a.date.localeCompare(b.date))
}

export const INTERVALS = {
  t1: golden.intervals_days['T1_first_GP_visit_to_KOC_referral'] ?? null,
  t2: golden.intervals_days['T2_KOC_referral_to_MDT'] ?? null,
  t3: golden.intervals_days['T3_MDT_to_oncology_consult'] ?? null,
}
