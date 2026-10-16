// Converts the rich mock view-models into the shape of contracts/openapi.json so that the MSW handlers exercise
// the same adapter as the real backend. Fields the contract does not have (diagnosis, GP, KOC…) are dropped here.
import type { components } from '@/lib/api/schema'
import type { CaseState } from '@/lib/domain'
import { ALENA_ID, type MockCase } from './cases'
import { DOCUMENTS } from './documents'

type ApiCase = components['schemas']['CaseSummary']
type ApiDetail = components['schemas']['CaseDetail']
type Role = components['schemas']['Role']

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
    baton_holder: c.baton && role ? { display: c.baton.name, id: `mock-${role}`, role } : null,
    next_deadline: c.baton?.due ? `${c.baton.due}T12:00:00+02:00` : null,
    opened_at: `${c.referredAt}T09:30:00+02:00`,
    document_count: c.id === ALENA_ID ? DOCUMENTS.length : 0,
    missing_count: c.counts.missing,
    conflict_count: c.counts.conflict,
  }
}

export function toApiDetail(c: MockCase, today: string): ApiDetail {
  return {
    ...toApiCase(c, today),
    documents:
      c.id === ALENA_ID
        ? DOCUMENTS.map((d) => ({
            doc_id: d.id,
            title: d.title,
            custodian: d.place,
            authored_at: d.authored,
            received_at: d.received,
          }))
        : [],
  }
}
