// MOCK copy – replaced by API in F2/F3
import type { TaskItem, TaskPhase } from '@/lib/domain'

const BASE: Array<Omit<TaskItem, 'state' | 'phase'>> = [
  { id: 't-req', title: 'Vyžádat výsledky 01–06', owner: 'Bc. Dvořáková', place: 'KOC 2 – koordinace', due: '2026-10-06', doneOn: '2026-10-08', dependsOn: [], lane: 'coordinator' },
  { id: 't-ct', title: 'CT hrudníku a břicha (pankreatický protokol)', owner: 'KOC 1 – radiologie', place: 'KOC 1 – Nemocnice Severní', due: '2026-10-08', doneOn: '2026-10-08', dependsOn: [], lane: 'external' },
  { id: 't-eus', title: 'EUS-FNB', owner: 'KOC 2 – endoskopie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-12', doneOn: '2026-10-12', dependsOn: ['t-ct'], lane: 'koc_physician' },
  { id: 't-lab', title: 'Odběry vč. nádorových markerů', owner: 'KOC 2 – laboratoř', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-15', doneOn: '2026-10-15', dependsOn: [], lane: 'external' },
  { id: 't-hist', title: 'Histologie', owner: 'KOC 2 – patologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-15', doneOn: '2026-10-19', dependsOn: ['t-eus'], lane: 'external' },
  { id: 't-verify', title: 'Ověřit rozpor v datech (apixaban, datum odběru)', owner: 'Bc. Dvořáková', place: 'KOC 2 – koordinace', due: '2026-10-21', dependsOn: ['t-hist'], lane: 'coordinator' },
  { id: 't-algo', title: 'Algeziologické vyšetření', owner: 'KOC 2 – algeziologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-26', doneOn: '2026-10-26', dependsOn: [], lane: 'koc_physician' },
  { id: 't-psy', title: 'Psychologické vyšetření', owner: 'KOC 2 – psychologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-27', doneOn: '2026-10-27', dependsOn: [], lane: 'koc_physician' },
]

/**
 * Tasks of the started set. Before the coordinator starts it (demo step 4 on 2. 10.) there are none; afterwards a
 * task is done by date (history) or by the phase the user advanced it to.
 */
export function tasksAt(today: string, setStarted = false, phases: Record<string, TaskPhase> = {}): TaskItem[] {
  if (today <= '2026-10-02' && !setStarted) return []
  return BASE.map((t) => {
    const byDate = t.doneOn !== undefined && t.doneOn <= today
    const phase: TaskPhase = byDate ? 'result_delivered' : (phases[t.id] ?? 'to_order')
    const done = phase === 'result_delivered'
    const state: TaskItem['state'] = done ? 'done' : t.due < today ? 'overdue' : 'open'
    return { ...t, state, phase, doneOn: byDate ? t.doneOn : undefined }
  })
}

/** Earliest due date among tasks not done yet, honouring the phases the user has already advanced. */
export function nextDeadline(today: string, phases: Record<string, TaskPhase> = {}): { title: string; due: string; owner: string } | null {
  const open = tasksAt(today, true, phases)
    .filter((t) => t.state !== 'done')
    .sort((a, b) => a.due.localeCompare(b.due))[0]
  return open ? { title: open.title, due: open.due, owner: open.owner } : null
}
