// MOCK copy – replaced by API in F2/F3
import type { CaseState, TaskPhase } from '@/lib/domain'
import { daysUntil } from '@/lib/date'
import { countFindings } from './findings'
import { INTERVALS } from './timeline'
import { nextDeadline } from './tasks'
import { DEMO_USERS } from './people'

/** Rich fixture case (portal endpoints return it as is; /api/cases* converts it to the contract shape). */
export interface MockCase {
  id: string
  patientName: string
  birthDate: string
  birthNumber: string
  insurer: string
  diagnosis: string
  state: CaseState
  subStatus: string
  column: 'new' | 'active' | 'snoozed'
  baton: { name: string; action: string; due: string | null }
  counts: { missing: number; conflict: number; stale: number }
  koc: string
  gp: string
  urgent: boolean
  referredAt: string
  t: { t1: number | null; t2: number | null; t3: number | null }
}

export const ALENA_ID = 'rakathon-2026-prochazkova'

export interface RowEdit {
  value: string
  reason: string
  by: string
  at: string
}

export interface MockStore {
  claimed: string[]
  acknowledged: string[]
  feedbackSent: boolean
  mdtGeneratedAt: string | null
  /** The conclusion a physician signed through `record_mdt_conclusion`. */
  conclusion: { text: string; by: string; signedAt: string } | null
  /** The coordinator closed the case (`close`). */
  closed: boolean
  /** The physician marked the case ready for the MDT (`mark_ready_mdt`). */
  markedReady: boolean
  confirmed: Record<string, string>
  extraCases: MockCase[]
  /** ids of document requests the coordinator has sent. */
  requested: string[]
  setStarted: boolean
  taskPhase: Record<string, TaskPhase>
  /** Clinician edits by section key and row index; every correction keeps its own reason, author and time. */
  edits: Record<string, Record<number, RowEdit>>
}

export function newStore(): MockStore {
  return {
    claimed: [],
    acknowledged: [],
    feedbackSent: false,
    mdtGeneratedAt: null,
    conclusion: null,
    closed: false,
    markedReady: false,
    confirmed: {},
    extraCases: [],
    requested: [],
    setStarted: false,
    taskPhase: {},
    edits: {},
  }
}

const COORD = DEMO_USERS.coordinator.name

function alena(today: string, s: MockStore): MockCase | null {
  if (today < '2026-10-02') return null
  let state: CaseState
  let subStatus: string
  let baton: MockCase['baton']
  if (s.closed || (s.feedbackSent && s.acknowledged.includes(ALENA_ID))) {
    state = 'uzavreno'
    subStatus = 'Uzavřeno – převzetí potvrzeno PL'
    baton = { name: 'Nikdo – případ uzavřen', action: 'Archivováno s auditní stopou', due: null }
  } else if (s.feedbackSent) {
    state = 'zpetna_vazba_odeslana'
    subStatus = 'Závěr MDT odeslán PL, čeká na potvrzení přijetí'
    baton = { name: `${DEMO_USERS.gp.name} (PL)`, action: 'Potvrdit přijetí závěru MDT', due: '2026-10-23' }
  } else if (s.conclusion) {
    state = 'zaver_mdt'
    subStatus = 'Závěr MDT zapsán – čeká na odeslání PL'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: 'Odeslat závěr PL', due: '2026-10-22' }
  } else if (today === '2026-10-21' || (s.markedReady && today >= '2026-10-19')) {
    state = 'pripraveno_mdt'
    subStatus = 'MDT dnes 8:00 – handover k as-of 21. 10. 2026'
    baton = { name: 'MDT KOC 2', action: 'Projednat případ', due: '2026-10-21' }
  } else if (today >= '2026-10-19') {
    state = 'kompletni'
    subStatus = 'Kompletní – čeká na potvrzení sekcí lékařem'
    baton = { name: `${DEMO_USERS.physician.name} (lékař KOC 2)`, action: 'Potvrdit handover', due: '2026-10-21' }
  } else if (today === '2026-10-02' && !s.claimed.includes(ALENA_ID)) {
    state = 'odeslano'
    subStatus = 'Nová žádost od PL – čeká na převzetí'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: 'Převzít případ', due: '2026-10-05' }
  } else if (today === '2026-10-02' && s.requested.length > 0) {
    state = 'ceka_na_podklady'
    subStatus = 'Čeká na podklady – vyžádány výsledky 01–06'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: 'Doplnit chybějící podklady', due: '2026-10-09' }
  } else if (today === '2026-10-02') {
    state = 'triage'
    subStatus = 'V triage → Čeká na podklady (výsledky 01–06 nejsou přiloženy)'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: 'Vyžádat výsledky 01–06', due: '2026-10-06' }
  } else {
    const nd = nextDeadline(today, s.taskPhase)
    state = 'ceka_na_podklady'
    subStatus = nd ? `Čeká na podklady – další krok: ${nd.title}` : 'Čeká na podklady'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: nd?.title ?? 'Doplnit podklady', due: nd?.due ?? null }
  }
  const t2 = today >= '2026-10-21' ? INTERVALS.t2 : daysUntil(today, '2026-10-02')
  return {
    id: ALENA_ID,
    patientName: 'Alena Procházková',
    birthDate: '1963-07-22',
    birthNumber: '635722/1013',
    insurer: '211 – Zdravotní pojišťovna ministerstva vnitra ČR',
    diagnosis: 'C25.0 – suspektní tumor hlavy pankreatu',
    state,
    subStatus,
    column: state === 'odeslano' || state === 'triage' ? 'new' : 'active',
    baton,
    counts: countFindings(today),
    koc: 'KOC 2 – Nemocnice Lipová',
    gp: DEMO_USERS.gp.name,
    urgent: true,
    referredAt: '2026-10-02',
    t: { t1: INTERVALS.t1, t2, t3: s.feedbackSent ? INTERVALS.t3 : null },
  }
}

const OTHERS: MockCase[] = [
  { id: 'c-kralova', patientName: 'Marie Králová', birthDate: '1971-03-09', birthNumber: '715309/2204', insurer: '111 – VZP ČR', diagnosis: 'C18.9 – suspektní tumor tlustého střeva', state: 'odeslano', subStatus: 'Nová žádost od PL – čeká na převzetí', column: 'new', baton: { name: 'Koordinátorka KOC 2', action: 'Převzít případ', due: '2026-10-19' }, counts: { missing: 2, conflict: 0, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: DEMO_USERS.gp.name, urgent: false, referredAt: '2026-10-16', t: { t1: 12, t2: 0, t3: null } },
  { id: 'c-svoboda', patientName: 'Petr Svoboda', birthDate: '1955-11-30', birthNumber: '551130/0987', insurer: '201 – VoZP ČR', diagnosis: 'C61 – suspektní nález prostaty', state: 'triage', subStatus: 'V triage – posuzuje koordinátorka', column: 'new', baton: { name: DEMO_USERS.coordinator.name, action: 'Dokončit triage', due: '2026-10-20' }, counts: { missing: 1, conflict: 0, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Novotná', urgent: false, referredAt: '2026-10-15', t: { t1: 20, t2: 1, t3: null } },
  { id: 'c-dvorak', patientName: 'Jan Dvořák', birthDate: '1960-05-14', birthNumber: '600514/1456', insurer: '205 – ČPZP', diagnosis: 'C34.9 – suspektní nález plic', state: 'kompletni', subStatus: 'Kompletní – čeká na lékaře KOC', column: 'active', baton: { name: DEMO_USERS.physician.name, action: 'Potvrdit handover', due: '2026-10-22' }, counts: { missing: 0, conflict: 1, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Novotná', urgent: false, referredAt: '2026-09-28', t: { t1: 25, t2: 18, t3: null } },
  { id: 'c-maresova', patientName: 'Eva Marešová', birthDate: '1968-01-25', birthNumber: '685125/3310', insurer: '207 – OZP', diagnosis: 'C50.9 – suspektní nález prsu', state: 'ceka_na_podklady', subStatus: 'Odloženo do 30. 10. 2026 – čeká na pacientku', column: 'snoozed', baton: { name: 'Pacientka', action: 'Dodat zprávy z mamologie', due: '2026-10-30' }, counts: { missing: 2, conflict: 0, stale: 1 }, koc: 'KOC 2 – Nemocnice Lipová', gp: DEMO_USERS.gp.name, urgent: false, referredAt: '2026-10-05', t: { t1: 9, t2: 11, t3: null } },
  { id: 'c-horakova', patientName: 'Ludmila Horáková', birthDate: '1952-08-03', birthNumber: '525803/0612', insurer: '211 – ZP MV ČR', diagnosis: 'C20 – tumor rekta', state: 'zpetna_vazba_odeslana', subStatus: 'Závěr MDT odeslán PL, čeká na potvrzení přijetí', column: 'active', baton: { name: `${DEMO_USERS.gp.name} (PL)`, action: 'Potvrdit přijetí závěru MDT', due: '2026-10-19' }, counts: { missing: 0, conflict: 0, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: DEMO_USERS.gp.name, urgent: false, referredAt: '2026-09-14', t: { t1: 18, t2: 19, t3: 12 } },
  { id: 'c-benes', patientName: 'Karel Beneš', birthDate: '1949-12-12', birthNumber: '491212/0321', insurer: '211 – ZP MV ČR', diagnosis: 'C15.9 – tumor jícnu', state: 'uzavreno', subStatus: 'Uzavřeno – převzetí potvrzeno PL', column: 'active', baton: { name: 'Nikdo – případ uzavřen', action: 'Archivováno', due: null }, counts: { missing: 0, conflict: 0, stale: 0 }, koc: 'KOC 1 – Nemocnice Severní', gp: DEMO_USERS.gp.name, urgent: false, referredAt: '2026-08-10', t: { t1: 22, t2: 17, t3: 13 } },
]

export function allCases(today: string, s: MockStore): MockCase[] {
  const a = alena(today, s)
  const others = OTHERS.filter((c) => c.referredAt <= today).map((c) =>
    c.state === 'odeslano' && s.claimed.includes(c.id)
      ? { ...c, state: 'triage' as const, subStatus: 'V triage – posuzuje koordinátorka', baton: { name: `${COORD} (koordinátorka KOC 2)`, action: 'Dokončit triage', due: c.baton.due } }
      : c.state === 'zpetna_vazba_odeslana' && s.acknowledged.includes(c.id)
      ? { ...c, state: 'uzavreno' as const, subStatus: 'Uzavřeno – převzetí potvrzeno PL', baton: { name: 'Nikdo – případ uzavřen', action: 'Archivováno s auditní stopou', due: null } }
      : c,
  )
  return [...(a ? [a] : []), ...s.extraCases, ...others]
}

export function caseById(id: string, today: string, s: MockStore): MockCase | undefined {
  return allCases(today, s).find((c) => c.id === id)
}

/**
 * Cases in the coordinator inbox (closed ones are archived). A case whose feedback was sent stays listed (bucket
 * `aktivni`, contracts/case-states.md) until the coordinator closes it: the queue is her way back to „Uzavřít případ“.
 */
export function inboxCases(today: string, s: MockStore): MockCase[] {
  return allCases(today, s).filter((c) => c.state !== 'uzavreno')
}
