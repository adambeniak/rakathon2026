// Case list and detail, the claim transition and the triage document requests (demo steps 1–2), on the contract paths.
// Findings, timeline, messages and audit are not in contracts/openapi.json: their handlers keep the provisional paths.
import { http, HttpResponse } from 'msw'
import type { components } from '@/lib/api/schema'
import { toApiCase, toApiDetail } from '../fixtures/api'
import { ALENA_ID, allCases, caseById, inboxCases, newStore } from '../fixtures/cases'
import { DOCUMENTS } from '../fixtures/documents'
import { activeFindings } from '../fixtures/findings'
import { AUDIT, MESSAGES } from '../fixtures/messages'
import { store } from '../fixtures/store'
import { timelineAt } from '../fixtures/timeline'
import { problem, roleOf, todayOf } from './util'
import { DEMO_USERS } from '../fixtures/people'

type Schemas = components['schemas']

const isAlena = (id: string | readonly string[] | undefined) => id === ALENA_ID

const GP = DEMO_USERS.gp.name // the demo GP of the mock cases (`MockCase.gp`)

const LETTER = '07_PL_zadost_KOC2_2026-10-02'

// The five reports the GP's letter lists (numbered lines of report 07), in the backend's order; the GP's own epicrisis
// (04) is not among them. The evidence quote is the verbatim numbered line, `label` the same without its number.
const LISTED = [
  { doc: '02_Laborator_2026-09-01', exam: '2026-09-01', org: 'labjih', recipient: 'Laboratoř LabJih', by: 'organization', label: 'Laboratorní vyšetření 1. 9. 2026 – krevní obraz, biochemie, moč chemicky a sediment, kultivace moči (LabJih)' },
  { doc: '03_RTG_plic_2026-09-03', exam: '2026-09-03', org: 'rc-modrany', recipient: 'Radiologické centrum Modřany', by: 'organization', label: 'RTG plic 3. 9. 2026 (Radiologické centrum Modřany)' },
  { doc: '05_Gastroenterologie_2026-09-15', exam: '2026-09-15', org: 'poliklinika-jizni', recipient: 'Poliklinika Jižní', by: 'organization', label: 'Gastroenterologické vyšetření 15. 9. 2026 (MUDr. Ivana Křížová, Poliklinika Jižní)' },
  { doc: '06_UZ_bricha_2026-09-29', exam: '2026-09-29', org: 'poliklinika-jizni', recipient: 'Poliklinika Jižní', by: 'organization', label: 'UZ břicha 29. 9. 2026 (RDG pracoviště, Poliklinika Jižní)' },
  { doc: '01_Kardiologie_2026-07-20', exam: '2026-07-20', org: 'kardio-jesenice', recipient: 'Kardiologická ambulance Jesenice', by: 'practitioner', label: 'Kardiologická kontrola 20. 7. 2026 (MUDr. Petr Malý)' },
] as const

const received = (doc: string) => DOCUMENTS.find((d) => d.id === doc)?.received.slice(0, 10)
const requestId = (doc: string) => `req-${doc}`

function proposals(today: string): Schemas['ProposalsOut'] {
  return {
    source_doc_id: LETTER,
    proposals: LISTED.map((l, i) => {
      const arrived = (received(l.doc) ?? '9999') <= today
      return {
        key: `${l.exam}-${i + 1}`,
        label: l.label,
        exam_date: l.exam,
        status: arrived ? 'attached' : 'missing',
        attached_doc_id: arrived ? l.doc : null,
        recipient_org_id: l.org,
        recipient_name: l.recipient,
        resolved_by: l.by,
        evidence: [{ doc_id: LETTER, quote: `${i + 1}. ${l.label}` }],
      }
    }),
  }
}

function requests(): Schemas['DocumentRequestOut'][] {
  return LISTED.filter((l) => store.requested.includes(requestId(l.doc))).map((l) => ({
    id: requestId(l.doc),
    label: l.label,
    recipient: l.recipient,
    exam_date: l.exam,
    due: '2026-10-06T12:00:00+02:00',
    status: 'requested',
  }))
}

/** Items the mock gate blocks on (the demo case has no ECOG). */
const MOCK_BLOCKING = ['performance_status']

/** `guard_failed` like the backend: Czech title, the reason in `detail` (for people), `code` and the structured
 * `blocking_items` (readiness item keys) for the machine. */
const guardFailed = (detail: string, blockingItems: string[]) => {
  const body: Schemas['ProblemDetails'] = {
    type: 'https://stafeta.example/problems/conflict',
    title: 'Podmínky akce nejsou splněny',
    status: 409,
    detail,
    code: 'guard_failed',
    blocking_items: blockingItems,
  }
  return HttpResponse.json(body, { status: 409, headers: { 'Content-Type': 'application/problem+json' } })
}

/** A role that may not fire the event, like the backend (#136): 403 `forbidden` with the shared title, `code` kept. */
const roleDenied = (detail: string) => {
  const body: Schemas['ProblemDetails'] = {
    type: 'https://stafeta.example/problems/forbidden',
    title: 'Přístup byl odepřen',
    status: 403,
    detail,
    code: 'forbidden_role',
  }
  return HttpResponse.json(body, { status: 403, headers: { 'Content-Type': 'application/problem+json' } })
}

export const handlers = [
  http.get('/api/cases', ({ request }) => {
    const today = todayOf(request)
    // The GP portal lists only the demo GP's own cases; the queue lists every case that is not closed.
    const list = roleOf(request) === 'gp' ? allCases(today, store).filter((c) => c.gp === GP) : inboxCases(today, store)
    return HttpResponse.json(list.map((c) => toApiCase(c, today)))
  }),
  http.get('/api/cases/:id', ({ params, request }) => {
    const c = caseById(String(params.id), todayOf(request), store)
    return c ? HttpResponse.json(toApiDetail(c, todayOf(request))) : problem(404, 'Případ nebyl nalezen')
  }),
  http.get('/api/cases/:id/findings', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? activeFindings(todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/timeline', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? timelineAt(todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/messages', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? MESSAGES.filter((m) => m.at.slice(0, 10) <= todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/audit', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? AUDIT.filter((a) => a.at.slice(0, 10) <= todayOf(request)) : []),
  ),
  http.get('/api/cases/:id/document-requests/proposals', ({ params, request }) =>
    HttpResponse.json(isAlena(params.id) ? proposals(todayOf(request)) : { source_doc_id: null, proposals: [] }),
  ),
  http.get('/api/cases/:id/document-requests', ({ params }) => HttpResponse.json(isAlena(params.id) ? requests() : [])),
  http.post('/api/cases/:id/document-requests', async ({ params, request }) => {
    if (roleOf(request) !== 'coordinator') return problem(403, 'Podklady může vyžádat pouze koordinátorka')
    const body = (await request.json()) as Schemas['DocumentRequestsBody']
    const wanted = LISTED.filter((l) => body.items.some((i) => i.label === l.label && i.recipient_org_id === l.org))
    if (wanted.length === 0) return problem(422, 'Vyberte alespoň jeden dokument')
    for (const l of wanted) if (!store.requested.includes(requestId(l.doc))) store.requested.push(requestId(l.doc))
    const today = todayOf(request)
    const created: Schemas['DocumentRequestsCreated'] = {
      case: toApiCase(caseById(String(params.id), today, store)!, today),
      requests: requests().filter((r) => wanted.some((l) => requestId(l.doc) === r.id)),
    }
    return HttpResponse.json(created, { status: 201 })
  }),
  http.post('/api/cases/:id/transitions', async ({ params, request }) => {
    const id = String(params.id)
    const today = todayOf(request)
    const c = caseById(id, today, store)
    if (!c) return problem(404, 'Případ nebyl nalezen')
    const { event, conclusion, waivers } = (await request.json()) as Schemas['app__api__schemas__workflow__TransitionRequest']
    if (event === 'gp_opened') {
      // The GP's read receipt: no state change, only while the feedback is out and not yet closed.
      if (roleOf(request) !== 'gp') return roleDenied('Otevření závěru potvrzuje pouze praktický lékař')
      if (c.state !== 'zpetna_vazba_odeslana') return problem(409, 'Zpětná vazba není ve stavu k otevření')
      return HttpResponse.json(toApiCase(c, today))
    }
    // Demo step 5-6 loop; the guards mirror the state machine (case_machine.py), the texts are the mock's.
    if (event === 'mark_ready_mdt') {
      if (roleOf(request) !== 'physician') return roleDenied('Připravenost k MDT označuje pouze lékař KOC')
      if (c.state !== 'kompletni') return problem(409, 'Přechod není ve stavu případu povolen')
      // The server's gate, as the mock plays it: the ECOG is missing in the demo case, so it blocks unless waived.
      const open = MOCK_BLOCKING.filter((item) => !(waivers ?? []).some((w) => w.item === item && w.reason.trim()))
      if (open.length > 0) return guardFailed(`Připravenost k MDT není splněna, chybí: ${open.join(', ')}`, open)
      store.markedReady = true
      return HttpResponse.json(toApiCase(caseById(id, today, store)!, today))
    }
    if (event === 'record_mdt_conclusion') {
      if (roleOf(request) !== 'physician') return roleDenied('Závěr MDT může zapsat pouze lékař KOC')
      if (c.state !== 'pripraveno_mdt') return problem(409, 'Přechod není ve stavu případu povolen')
      if (today < '2026-10-21') return problem(409, 'Splněná podmínka přechodu: MDT ještě nezačalo')
      if (!conclusion?.trim()) return problem(422, 'Závěr MDT je povinný')
      store.conclusion = { text: conclusion.trim(), by: DEMO_USERS.physician.name, signedAt: `${today}T09:30:00+02:00` }
      return HttpResponse.json(toApiCase(caseById(id, today, store)!, today))
    }
    if (event === 'send_feedback') {
      if (roleOf(request) !== 'coordinator') return roleDenied('Závěr odesílá pouze koordinátorka')
      if (c.state !== 'zaver_mdt') return problem(409, 'Přechod není ve stavu případu povolen')
      store.feedbackSent = true
      return HttpResponse.json(toApiCase(caseById(id, today, store)!, today))
    }
    if (event === 'close') {
      if (roleOf(request) !== 'coordinator') return roleDenied('Případ uzavírá pouze koordinátorka')
      if (c.state !== 'zpetna_vazba_odeslana') return problem(409, 'Přechod není ve stavu případu povolen')
      store.closed = true
      return HttpResponse.json(toApiCase(caseById(id, today, store)!, today))
    }
    if (event !== 'accept') return problem(422, 'Událost není v této ukázce podporována')
    if (roleOf(request) !== 'coordinator') return roleDenied('Případ smí převzít pouze koordinátorka')
    if (c.state !== 'odeslano') return problem(409, 'Případ už byl převzat')
    store.claimed.push(id)
    return HttpResponse.json(toApiCase(caseById(id, today, store)!, today))
  }),
  http.post('/api/mock/reset', () => {
    Object.assign(store, newStore())
    return HttpResponse.json({ ok: true, cases: allCases('2026-10-16', store).length })
  }),
]
