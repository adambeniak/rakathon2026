// Demo step 1 on the contract paths: KOC directory, referral prefill from an uploaded letter, referral submit.
import { http, HttpResponse } from 'msw'
import type { components } from '@/lib/api/schema'
import { toApiCase } from '../fixtures/api'
import { ALENA_ID, caseById, newStore } from '../fixtures/cases'
import { KOC_DIRECTORY } from '../fixtures/people'
import { problem, roleOf } from './util'

type Schemas = components['schemas']
type Prefill = Schemas['ReferralPrefill']

// The mock reads any uploaded letter as report 07 (the real backend takes the document id from the file name).
const LETTER_DOC_ID = '07_PL_zadost_KOC2_2026-10-02'

// Not `instanceof File`: under jsdom the request body is parsed by Node's fetch, whose File class is not jsdom's.
const isFile = (part: FormDataEntryValue | null): part is File => typeof part === 'object' && part !== null && 'name' in part

/** Every quote is a verbatim line of report 07 (the GP's letter); nothing is quoted from another report. */
function evidenced<T>(value: T, docId: string, quote: string, derived = false) {
  return { value, status: 'complete' as const, derived, evidence: [{ doc_id: docId, quote }] }
}

function prefill(): Prefill {
  const doc = LETTER_DOC_ID
  const name = 'Pacientka: Alena Procházková'
  const rc = 'Rodné číslo: 635722/1013'
  return {
    doc_id: doc,
    authored_at: '2026-10-02',
    given: evidenced('Alena', doc, name),
    family: evidenced('Procházková', doc, name),
    sex: evidenced('female', doc, rc, true),
    birth_date: evidenced('1963-07-22', doc, 'Datum narození: 22. 7. 1963 (63 let)'),
    age_text: evidenced('63 let', doc, 'Datum narození: 22. 7. 1963 (63 let)'),
    birth_number: evidenced('635722/1013', doc, rc),
    birth_number_checksum_valid: true,
    address: evidenced({ line: 'Za Školou 17', postal_code: '252 41', city: 'Dolní Břežany', country: 'CZ' }, doc, 'Bydliště: Za Školou 17, 252 41 Dolní Břežany'),
    patient_phone: evidenced('+420 777 000 541', doc, 'Telefon: +420 777 000 541'),
    insurer_code: evidenced('211', doc, 'Zdravotní pojišťovna: 211'),
    insurer_name: 'Zdravotní pojišťovna ministerstva vnitra České republiky',
    contact_person: evidenced({ name: 'Petra Horká', relation: 'dcera', phone: '+420 777 000 542' }, doc, 'Kontaktní osoba: Petra Horká (dcera), tel. +420 777 000 542'),
    requesting_gp: evidenced('MUDr. Tomáš Řezníček', doc, 'MUDr. Tomáš Řezníček'),
    suspected_diagnosis: evidenced({ code: 'C25.0', text: 'suspektní tumor hlavy pankreatu' }, doc, 'C25.0 – suspektní tumor hlavy pankreatu'),
    consent_statements: [evidenced('Souhlasí se sdílením informací s dcerou.', doc, 'Souhlasí se sdílením informací s dcerou.')],
    urgency_statement: evidenced('prosím o urgentní řešení', doc, 'prosím o urgentní řešení'),
  }
}

export const handlers = [
  http.get('/api/directory/kocs', () => HttpResponse.json(KOC_DIRECTORY)),
  http.post('/api/referrals/prefill', async ({ request }) => {
    const letter = (await request.formData()).get('letter')
    if (!isFile(letter)) return problem(422, 'Chybí soubor žádosti')
    return HttpResponse.json(prefill())
  }),
  http.post('/api/referrals', async ({ request }) => {
    if (roleOf(request) !== 'gp') return problem(403, 'Žádost může odeslat pouze praktický lékař')
    const form = await request.formData()
    const payload = JSON.parse(String(form.get('payload') ?? '{}')) as { consent_confirmed?: boolean }
    if (!isFile(form.get('letter')) || payload.consent_confirmed !== true) return problem(422, 'Chybí žádost nebo souhlas pacienta')
    const created = caseById(ALENA_ID, '2026-10-02', newStore())!
    const body: Schemas['ReferralCreated'] = {
      case: {
        ...toApiCase(created, '2026-10-02'),
        baton_holder: { id: 'dvorakova-lucie@koc2-nemocnice-lipova', display: 'Koordinátor KOC 2', role: 'coordinator' },
      },
      warnings: [],
    }
    return HttpResponse.json(body, { status: 201 })
  }),
]
