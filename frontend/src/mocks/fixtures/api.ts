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
type ApiReviewerCase = components['schemas']['ReviewerCase']

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

type CaseAction = components['schemas']['CaseAction']

// Next action of the baton role (backend `Case.next_action`, app/domain/case.py).
const ACTION: Record<CaseState, CaseAction> = {
  odeslano: 'accept_case',
  triage: 'triage',
  ceka_na_podklady: 'complete_documents',
  kompletni: 'review_handover',
  pripraveno_mdt: 'hold_mdt',
  zaver_mdt: 'send_feedback',
  zpetna_vazba_odeslana: 'confirm_receipt',
  uzavreno: 'none',
}

function batonOf(c: MockCase, role: Role | null): ApiCase['baton'] {
  if (c.state === 'uzavreno') return { role: null, action: 'none' }
  if (c.column === 'snoozed') return { role: 'external_workplace', action: 'await_external' }
  if (c.state === 'zpetna_vazba_odeslana' && role === 'coordinator') return { role, action: 'close_case' }
  return { role, action: ACTION[c.state] }
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
  const role = c.batonRole ?? BATON_ROLE[c.state]
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
    baton: batonOf(c, role),
    next_deadline: c.baton?.due ? `${c.baton.due}T12:00:00+02:00` : null,
    opened_at: `${c.referredAt}T09:30:00+02:00`,
    document_count: c.id === ALENA_ID ? arrived(today).length : 0,
    missing_count: c.counts.missing,
    conflict_count: c.counts.conflict,
    counts: { missing: c.counts.missing, conflict: c.counts.conflict, stale: c.counts.stale },
    gp_opened_at: c.gpOpenedAt ?? null,
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
    readiness_waivers: c.readinessWaivers ?? [],
    intervals: toApiIntervals(c),
  }
}

// A stable mock pseudonym (the backend uses a keyed HMAC of the case id; the case id itself carries the surname).
function mockRef(id: string): string {
  let a = 0x811c9dc5
  let b = 0x01000193
  for (const ch of id) {
    a = Math.imul(a ^ ch.charCodeAt(0), 0x01000193) >>> 0
    b = Math.imul(b ^ ch.charCodeAt(0), 0x85ebca6b) >>> 0
  }
  return `RV-${(a.toString(16).padStart(8, '0') + b.toString(16).padStart(8, '0')).slice(0, 12).toUpperCase()}`
}

const FEEDBACK_SENT: ReadonlySet<CaseState> = new Set(['zpetna_vazba_odeslana', 'uzavreno'])

/** The insurer reviewer's minimal view (backend/app/api/services/reviewer.py): no name, birth date or clinical text. */
export function toReviewerCase(c: MockCase): ApiReviewerCase {
  const [given = '', family = ''] = c.patientName.split(' ')
  return {
    ref: mockRef(c.id),
    initials: [given, family].filter(Boolean).map((p) => `${p[0]}.`).join(' '),
    birth_year: Number(c.birthDate.slice(0, 4)),
    insurer_code: c.insurer.slice(0, 3),
    diagnosis_category: /^[A-Z]\d{2}/.exec(c.diagnosis)?.[0] ?? null,
    state: c.state,
    referred_on: c.referredAt,
    intervals: toApiIntervals(c),
    delivery: { status: FEEDBACK_SENT.has(c.state) ? 'handed_over' : 'not_sent', gp_opened_on: null },
  }
}
