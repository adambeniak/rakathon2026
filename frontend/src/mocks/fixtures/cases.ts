import type { CaseDetail, CaseState, CaseSummary } from '@/lib/domain'
import { daysUntil } from '@/lib/date'
import { countFindings } from './findings'
import { INTERVALS } from './timeline'
import { nextDeadline } from './tasks'

export const ALENA_ID = 'rakathon-2026-prochazkova'

export interface MockStore {
  claimed: boolean
  acknowledged: boolean
  mdtGeneratedAt: string | null
  confirmed: Record<string, string>
  extraCases: CaseDetail[]
}

export function newStore(): MockStore {
  return { claimed: false, acknowledged: false, mdtGeneratedAt: null, confirmed: {}, extraCases: [] }
}

const COORD = 'Bc. Dvořáková'

function alena(today: string, s: MockStore): CaseDetail | null {
  if (today < '2026-10-02') return null
  let state: CaseState
  let subStatus: string
  let baton: CaseSummary['baton']
  if (s.acknowledged && today >= '2026-10-22') {
    state = 'closed'
    subStatus = 'Uzavřeno – převzetí potvrzeno PL'
    baton = { name: 'Nikdo – případ uzavřen', action: 'Archivováno s auditní stopou', due: null }
  } else if (today >= '2026-10-22') {
    state = 'feedback_sent'
    subStatus = 'Závěr MDT odeslán PL, čeká na potvrzení přijetí'
    baton = { name: 'MUDr. Řezníček (PL)', action: 'Potvrdit přijetí závěru MDT', due: '2026-10-23' }
  } else if (today === '2026-10-21') {
    state = 'ready_for_mdt'
    subStatus = 'MDT dnes 8:00 – handover k as-of 21. 10. 2026'
    baton = { name: 'MDT KOC 2', action: 'Projednat případ', due: '2026-10-21' }
  } else if (today >= '2026-10-19') {
    state = 'complete'
    subStatus = 'Kompletní – čeká na potvrzení sekcí lékařem'
    baton = { name: 'MUDr. Havelka (lékař KOC 2)', action: 'Potvrdit handover', due: '2026-10-21' }
  } else if (today === '2026-10-02' && !s.claimed) {
    state = 'sent'
    subStatus = 'Nová žádost od PL – čeká na převzetí'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: 'Převzít případ', due: '2026-10-05' }
  } else if (today === '2026-10-02') {
    state = 'triage'
    subStatus = 'V triage → Čeká na podklady (výsledky 01–06 nejsou přiloženy)'
    baton = { name: `${COORD} (koordinátorka KOC 2)`, action: 'Vyžádat výsledky 01–06', due: '2026-10-06' }
  } else {
    const nd = nextDeadline(today)
    state = 'awaiting_docs'
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
    column: state === 'sent' || state === 'triage' ? 'new' : 'active',
    baton,
    counts: countFindings(today),
    koc: 'KOC 2 – Nemocnice Lipová',
    gp: 'MUDr. Řezníček',
    urgent: true,
    referredAt: '2026-10-02',
    t: { t1: INTERVALS.t1, t2, t3: today >= '2026-10-22' ? INTERVALS.t3 : null },
  }
}

const OTHERS: CaseDetail[] = [
  { id: 'c-kralova', patientName: 'Marie Králová', birthDate: '1971-03-09', birthNumber: '715309/2204', insurer: '111 – VZP ČR', diagnosis: 'C18.9 – suspektní tumor tlustého střeva', state: 'sent', subStatus: 'Nová žádost od PL – čeká na převzetí', column: 'new', baton: { name: 'Koordinátorka KOC 2', action: 'Převzít případ', due: '2026-10-19' }, counts: { missing: 2, conflict: 0, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Řezníček', urgent: false, referredAt: '2026-10-16', t: { t1: 12, t2: 0, t3: null } },
  { id: 'c-svoboda', patientName: 'Petr Svoboda', birthDate: '1955-11-30', birthNumber: '551130/0987', insurer: '201 – VoZP ČR', diagnosis: 'C61 – suspektní nález prostaty', state: 'triage', subStatus: 'V triage – posuzuje koordinátorka', column: 'new', baton: { name: 'Bc. Dvořáková', action: 'Dokončit triage', due: '2026-10-20' }, counts: { missing: 1, conflict: 0, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Novotná', urgent: false, referredAt: '2026-10-15', t: { t1: 20, t2: 1, t3: null } },
  { id: 'c-dvorak', patientName: 'Jan Dvořák', birthDate: '1960-05-14', birthNumber: '600514/1456', insurer: '205 – ČPZP', diagnosis: 'C34.9 – suspektní nález plic', state: 'complete', subStatus: 'Kompletní – čeká na lékaře KOC', column: 'active', baton: { name: 'MUDr. Havelka', action: 'Potvrdit handover', due: '2026-10-22' }, counts: { missing: 0, conflict: 1, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Novotná', urgent: false, referredAt: '2026-09-28', t: { t1: 25, t2: 18, t3: null } },
  { id: 'c-maresova', patientName: 'Eva Marešová', birthDate: '1968-01-25', birthNumber: '685125/3310', insurer: '207 – OZP', diagnosis: 'C50.9 – suspektní nález prsu', state: 'awaiting_docs', subStatus: 'Odloženo do 30. 10. 2026 – čeká na pacientku', column: 'snoozed', baton: { name: 'Pacientka', action: 'Dodat zprávy z mamologie', due: '2026-10-30' }, counts: { missing: 2, conflict: 0, stale: 1 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Řezníček', urgent: false, referredAt: '2026-10-05', t: { t1: 9, t2: 11, t3: null } },
  { id: 'c-horakova', patientName: 'Ludmila Horáková', birthDate: '1952-08-03', birthNumber: '525803/0612', insurer: '211 – ZP MV ČR', diagnosis: 'C20 – tumor rekta', state: 'feedback_sent', subStatus: 'Závěr MDT odeslán PL, čeká na potvrzení přijetí', column: 'active', baton: { name: 'MUDr. Řezníček (PL)', action: 'Potvrdit přijetí závěru MDT', due: '2026-10-19' }, counts: { missing: 0, conflict: 0, stale: 0 }, koc: 'KOC 2 – Nemocnice Lipová', gp: 'MUDr. Řezníček', urgent: false, referredAt: '2026-09-14', t: { t1: 18, t2: 19, t3: 12 } },
  { id: 'c-benes', patientName: 'Karel Beneš', birthDate: '1949-12-12', birthNumber: '491212/0321', insurer: '211 – ZP MV ČR', diagnosis: 'C15.9 – tumor jícnu', state: 'closed', subStatus: 'Uzavřeno – převzetí potvrzeno PL', column: 'active', baton: { name: 'Nikdo – případ uzavřen', action: 'Archivováno', due: null }, counts: { missing: 0, conflict: 0, stale: 0 }, koc: 'KOC 1 – Nemocnice Severní', gp: 'MUDr. Řezníček', urgent: false, referredAt: '2026-08-10', t: { t1: 22, t2: 17, t3: 13 } },
]

export function allCases(today: string, s: MockStore): CaseDetail[] {
  const a = alena(today, s)
  return [...(a ? [a] : []), ...s.extraCases, ...OTHERS.filter((c) => c.referredAt <= today)]
}

export function caseById(id: string, today: string, s: MockStore): CaseDetail | undefined {
  return allCases(today, s).find((c) => c.id === id)
}

/** Cases in the coordinator inbox (closed ones are archived). */
export function inboxCases(today: string, s: MockStore): CaseDetail[] {
  return allCases(today, s).filter((c) => c.state !== 'closed' && c.state !== 'feedback_sent')
}
