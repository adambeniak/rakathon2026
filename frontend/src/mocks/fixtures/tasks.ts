// MOCK copy – replaced by API in F2/F3
import type { TaskItem } from '@/lib/domain'

const BASE: Array<Omit<TaskItem, 'state'>> = [
  { id: 't-req', title: 'Vyžádat výsledky 01–06', owner: 'Bc. Dvořáková', place: 'KOC 2 – koordinace', due: '2026-10-06', doneOn: '2026-10-08', dependsOn: [] },
  { id: 't-ct', title: 'CT hrudníku a břicha (pankreatický protokol)', owner: 'KOC 1 – radiologie', place: 'KOC 1 – Nemocnice Severní', due: '2026-10-08', doneOn: '2026-10-08', dependsOn: [] },
  { id: 't-eus', title: 'EUS-FNB', owner: 'KOC 2 – endoskopie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-12', doneOn: '2026-10-12', dependsOn: ['t-ct'] },
  { id: 't-lab', title: 'Odběry vč. nádorových markerů', owner: 'KOC 2 – laboratoř', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-15', doneOn: '2026-10-15', dependsOn: [] },
  { id: 't-hist', title: 'Histologie', owner: 'KOC 2 – patologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-15', doneOn: '2026-10-19', dependsOn: ['t-eus'] },
  { id: 't-verify', title: 'Ověřit rozpor v datech (apixaban, datum odběru)', owner: 'Bc. Dvořáková', place: 'KOC 2 – koordinace', due: '2026-10-21', dependsOn: ['t-hist'] },
  { id: 't-algo', title: 'Algeziologické vyšetření', owner: 'KOC 2 – algeziologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-26', doneOn: '2026-10-26', dependsOn: [] },
  { id: 't-psy', title: 'Psychologické vyšetření', owner: 'KOC 2 – psychologie', place: 'KOC 2 – Nemocnice Lipová', due: '2026-10-27', doneOn: '2026-10-27', dependsOn: [] },
]

export function tasksAt(today: string): TaskItem[] {
  return BASE.map((t) => {
    const done = t.doneOn !== undefined && t.doneOn <= today
    const state: TaskItem['state'] = done ? 'done' : t.due < today ? 'overdue' : 'open'
    return { ...t, state, doneOn: done ? t.doneOn : undefined }
  })
}

/** Earliest due date among tasks not done yet. */
export function nextDeadline(today: string): { title: string; due: string; owner: string } | null {
  const open = tasksAt(today)
    .filter((t) => t.state !== 'done')
    .sort((a, b) => a.due.localeCompare(b.due))[0]
  return open ? { title: open.title, due: open.due, owner: open.owner } : null
}
