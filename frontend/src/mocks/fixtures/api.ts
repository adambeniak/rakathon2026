// Converts the rich mock view-models into the shape of contracts/openapi.json so that the MSW handlers exercise
// the same adapter as the real backend. Fields the contract does not have (diagnosis, GP, KOC…) are dropped here.
import type { components } from '@/lib/api/schema'
import type { CaseState } from '@/lib/domain'
import { ALENA_ID, type MockCase } from './cases'
import { DOCUMENTS } from './documents'

type ApiCase = components['schemas']['CaseSummary']
type ApiDetail = components['schemas']['CaseDetail']
type Role = components['schemas']['Role']
type ApiIntervals = components['schemas']['TimeToTreatmentIntervals']

// Like backend/app/timeline/intervals.py: the MDT counts once it was held; the first GP visit and the oncology consult
// are not recorded (#188, #189), so T1 is `not_recorded` and T3 `running` after the MDT. No golden values here.
const MDT_HELD: ReadonlySet<CaseState> = new Set(['zaver_mdt', 'zpetna_vazba_odeslana', 'uzavreno'])

const addDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function toApiIntervals(c: MockCase): ApiIntervals {
  const referral = c.referredAt
  const mdt = MDT_HELD.has(c.state) && c.t.t2 !== null ? addDays(referral, c.t.t2) : null
  return {
    t1: { days: null, status: 'not_recorded', start: null, end: referral },
    t2: mdt
      ? { days: c.t.t2, status: 'measured', start: referral, end: mdt }
      : { days: null, status: 'running', start: referral, end: null },
    t3: mdt ? { days: null, status: 'running', start: mdt, end: null } : { days: null, status: 'not_started', start: null, end: null },
  }
}

// Baton role after entering a state (contracts/case-states.md).
const BATON_ROLE: Record<CaseState, Role | null> = {
  odeslano: 'coordinator',
  triage: 'coordinator',
  ceka_na_podklady: 'coordinator',
  kompletni: 'koc_physician',
  pripraveno_mdt: 'koc_physician',
  zaver_mdt: 'coordinator',
  zpetna_vazba_odeslana: 'gp',
  uzavreno: null,
}

// Only documents already received on the simulated day exist yet.
const arrived = (today: string) => DOCUMENTS.filter((d) => d.received.slice(0, 10) <= today)

const ageOn = (birth: string, today: string) => {
  const b = new Date(birth)
  const t = new Date(today)
  let age = t.getFullYear() - b.getFullYear()
  if (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate())) age -= 1
  return age
}

export function toApiCase(c: MockCase, today: string): ApiCase {
  const role = BATON_ROLE[c.state]
  return {
    id: c.id,
    patient: {
      display_name: c.patientName,
      birth_date: c.birthDate,
      age_years: ageOn(c.birthDate, today),
      sex: 'unknown',
      insurer_code: c.insurer.slice(0, 3),
    },
    state: c.state,
    // contracts/case-states.md: only `odeslano` is Nový; Odložený is the postponed flag; the rest is Aktivní.
    bucket: c.column === 'snoozed' ? 'odlozeny' : c.state === 'odeslano' ? 'novy' : c.state === 'uzavreno' ? 'archiv' : 'aktivni',
    postponed: c.column === 'snoozed',
    koc: c.koc,
    referring_gp: { name: c.gp },
    baton_holder: c.baton && role ? { display: c.baton.name, id: `mock-${role}`, role } : null,
    next_deadline: c.baton?.due ? `${c.baton.due}T12:00:00+02:00` : null,
    opened_at: `${c.referredAt}T09:30:00+02:00`,
    document_count: c.id === ALENA_ID ? arrived(today).length : 0,
    missing_count: c.counts.missing,
    conflict_count: c.counts.conflict,
    counts: { missing: c.counts.missing, conflict: c.counts.conflict, stale: c.counts.stale },
  }
}

export function toApiDetail(c: MockCase, today: string): ApiDetail {
  return {
    ...toApiCase(c, today),
    documents:
      c.id === ALENA_ID
        ? arrived(today).map((d) => ({
            doc_id: d.id,
            title: d.title,
            custodian: d.place,
            authored_at: d.authored,
            received_at: d.received,
          }))
        : [],
    intervals: toApiIntervals(c),
  }
}
