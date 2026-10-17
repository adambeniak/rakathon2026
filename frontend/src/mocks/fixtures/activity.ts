// MOCK copy of the case activity endpoints (audit, timeline, messages) in the contract shapes. The demo story of
// Alena Procházková by date, plus what the session did (claim, requests, readiness, conclusion, feedback, close).
import type { components } from '@/lib/api/schema'
import { pragueLocalToIso } from '@/lib/date'
import { ALENA_ID, type MockStore } from './cases'
import { AS_OF_DEFAULT, DOCUMENTS } from './documents'
import { DEMO_USERS } from './people'
import { LISTED, REQUESTED_AT, requestId } from './requests'

type Schemas = components['schemas']
type TimelineEntry = Schemas['TimelineEntry']
type AuditEntry = Schemas['AuditEntry']

const GP = DEMO_USERS.gp.name
const COORD = DEMO_USERS.coordinator.name
const PHYS = DEMO_USERS.physician.name
const SYSTEM = 'Štafeta (systém)'
const HISTOLOGY_STEP = 'Histologie z EUS-FNB'

interface CaseEvent {
  at: string
  event: string
  from: string | null
  to: string | null
  actor: string
  role: Schemas['Role']
  receipt?: string
}

const day = (iso: string) => iso.slice(0, 10)
const ms = (iso: string) => new Date(iso).getTime()
const RECEIPT = '<demo-feedback@stafeta.example>'

/** The case events of the story up to `today` (business time, like the backend's domain AuditEvents). */
function caseEvents(today: string, s: MockStore): CaseEvent[] {
  if (today < '2026-10-02') return []
  const events: CaseEvent[] = [
    {
      at: '2026-10-02T10:05:00+02:00',
      event: 'submit',
      from: null,
      to: 'odeslano',
      actor: GP,
      role: 'gp',
    },
  ]
  if (today > '2026-10-02' || s.claimed.includes(ALENA_ID))
    events.push({
      at: '2026-10-02T11:28:00+02:00',
      event: 'accept',
      from: 'odeslano',
      to: 'triage',
      actor: COORD,
      role: 'coordinator',
    })
  if (requested(today, s))
    events.push({
      at: REQUESTED_AT,
      event: 'request_documents',
      from: 'triage',
      to: 'ceka_na_podklady',
      actor: COORD,
      role: 'coordinator',
    })
  if (today >= '2026-10-19')
    events.push({
      at: '2026-10-19T12:10:00+02:00',
      event: 'docs_received',
      from: 'ceka_na_podklady',
      to: 'kompletni',
      actor: SYSTEM,
      role: 'system',
    })
  if (today >= '2026-10-21' || (s.markedReady && today >= '2026-10-19'))
    events.push({
      at: '2026-10-20T15:00:00+02:00',
      event: 'mark_ready_mdt',
      from: 'kompletni',
      to: 'pripraveno_mdt',
      actor: PHYS,
      role: 'koc_physician',
    })
  if (s.conclusion)
    events.push({
      at: s.conclusion.signedAt,
      event: 'record_mdt_conclusion',
      from: 'pripraveno_mdt',
      to: 'zaver_mdt',
      actor: PHYS,
      role: 'koc_physician',
    })
  if (s.feedbackSent) {
    const at = `${today}T10:00:00+02:00`
    events.push({
      at,
      event: 'send_feedback',
      from: 'zaver_mdt',
      to: 'zpetna_vazba_odeslana',
      actor: COORD,
      role: 'coordinator',
    })
    events.push({
      at,
      event: 'delivery_confirmed',
      from: 'zpetna_vazba_odeslana',
      to: 'zpetna_vazba_odeslana',
      actor: SYSTEM,
      role: 'system',
      receipt: RECEIPT,
    })
  }
  if (s.closed)
    events.push({
      at: `${today}T11:00:00+02:00`,
      event: 'close',
      from: 'zpetna_vazba_odeslana',
      to: 'uzavreno',
      actor: COORD,
      role: 'coordinator',
    })
  return events
}

function requested(today: string, s: MockStore): boolean {
  return today > '2026-10-02' || s.requested.length > 0
}

const knownDocuments = (today: string) => DOCUMENTS.filter((d) => day(d.received) <= today)

/** The backend's as-of rule against the MDT start: authored on/after its day or received after it. */
const afterMdt = (authored: string, received: string) =>
  authored >= day(AS_OF_DEFAULT) || ms(received) > ms(AS_OF_DEFAULT)

const CASE_KINDS: Record<string, TimelineEntry['kind']> = {
  record_mdt_conclusion: 'mdt_conclusion',
  send_feedback: 'feedback_sent',
  delivery_confirmed: 'feedback_delivered',
  gp_opened: 'gp_opened',
}

export function timelineFor(today: string, s: MockStore): Schemas['CaseTimeline'] {
  const now = `${today}T12:00:00+02:00`
  const base = { date_only: false, planned: false }
  const events: TimelineEntry[] = []
  for (const d of knownDocuments(today)) {
    const flag = {
      title: d.title,
      place: d.place,
      doc_id: d.id,
      excluded_from_handover: afterMdt(d.authored, d.received),
    }
    events.push({
      ...base,
      ...flag,
      id: `document_authored:${d.id}`,
      kind: 'document_authored',
      at: pragueLocalToIso(`${d.authored}T00:00`), // start of the Prague day (CET after 25. 10.)
      date_only: true,
    })
    events.push({
      ...base,
      ...flag,
      id: `document_received:${d.id}`,
      kind: 'document_received',
      at: d.received,
    })
  }
  if (requested(today, s)) {
    for (const l of LISTED) {
      events.push({
        ...base,
        id: `request-sent:${requestId(l.doc)}`,
        kind: 'request_sent',
        at: REQUESTED_AT,
        title: l.label,
        place: l.recipient,
        task_id: requestId(l.doc),
      })
      const doc = DOCUMENTS.find((d) => d.id === l.doc)
      if (doc && day(doc.received) <= today)
        events.push({
          ...base,
          id: `request-fulfilled:${requestId(l.doc)}`,
          kind: 'request_fulfilled',
          at: doc.received,
          title: l.label,
          task_id: requestId(l.doc),
          doc_id: doc.id,
        })
    }
  }
  if (today >= '2026-10-16')
    events.push({
      ...base,
      id: 'step-escalated:histology',
      kind: 'step_escalated',
      at: '2026-10-16T09:00:00+02:00',
      title: HISTOLOGY_STEP,
      place: 'KOC 2 – Nemocnice Lipová, patologie',
    })
  for (const [i, e] of caseEvents(today, s).entries()) {
    events.push({
      ...base,
      id: `case:${e.event}:${i}`,
      kind: CASE_KINDS[e.event] ?? 'case_event',
      at: e.at,
      event: e.event,
      actor: e.actor,
      from_state: e.from,
      to_state: e.to !== e.from ? e.to : null,
      receipt_id: e.receipt ?? null,
    })
  }
  events.push({
    ...base,
    id: 'mdt-meeting',
    kind: 'mdt_meeting',
    at: AS_OF_DEFAULT,
    planned: ms(AS_OF_DEFAULT) > ms(now),
  })
  events.sort((a, b) => ms(a.at) - ms(b.at) || a.id.localeCompare(b.id))
  return { case_id: ALENA_ID, as_of: AS_OF_DEFAULT, now, events }
}

export function messagesFor(today: string, s: MockStore): Schemas['CaseMessage'][] {
  const messages: Schemas['CaseMessage'][] = []
  if (requested(today, s)) {
    for (const l of LISTED) {
      const doc = DOCUMENTS.find((d) => d.id === l.doc)
      const arrived = doc !== undefined && day(doc.received) <= today
      messages.push({
        id: requestId(l.doc),
        kind: 'document_request',
        status: arrived ? 'fulfilled' : 'open',
        sent_at: REQUESTED_AT,
        sender: COORD,
        recipient: l.recipient,
        text: `Žádost o zaslání výsledku vyšetření: ${l.label}`,
        request: {
          request_id: requestId(l.doc),
          status: arrived ? 'completed' : 'requested',
          due: '2026-10-06T23:59:00+02:00',
          exam_date: l.exam,
          result_doc_id: arrived ? l.doc : null,
        },
        delivery: null,
      })
    }
  }
  if (s.feedbackSent) {
    messages.push({
      id: `${ALENA_ID}@feedback`,
      kind: 'mdt_feedback',
      status: 'sent',
      sent_at: `${today}T10:00:00+02:00`,
      sender: COORD,
      recipient: GP,
      text:
        'Dobrý den,\n\nKOC 2 – Nemocnice Lipová Vám zasílá zpětnou vazbu z jednání multidisciplinárního týmu (MDT) konaného 21. 10. 2026.\n\n' +
        'Zpětná vazba je k dispozici v portálu Štafeta. Obsah zprávy záměrně neuvádíme e-mailem.',
      request: null,
      delivery: {
        channel: 'email',
        receipt_id: RECEIPT,
        gp_opened_at: s.acknowledged.includes(ALENA_ID) ? `${today}T10:30:00+02:00` : null,
      },
    })
  }
  return messages
}

export function auditFor(
  today: string,
  s: MockStore,
  offset = 0,
  limit = 100,
): Schemas['CaseAuditTrail'] {
  const entry = (
    recorded: string,
    actor: string,
    role: Schemas['Role'],
    over: Partial<AuditEntry>,
  ): AuditEntry => ({
    recorded,
    actor,
    actor_role: role,
    on_behalf_of: null,
    action: 'R',
    operation: 'read',
    workflow_event: false,
    entity_types: ['Task', 'Patient', 'EpisodeOfCare'],
    outcome: 'success',
    ...over,
  })
  const items: AuditEntry[] = caseEvents(today, s).map((e) =>
    entry(e.at, e.actor, e.role, {
      action: e.event === 'submit' ? 'C' : 'U',
      operation: e.event,
      workflow_event: true,
      entity_types: ['Task'],
    }),
  )
  for (const d of knownDocuments(today))
    items.push(
      entry(d.received, COORD, 'coordinator', {
        action: 'E',
        operation: 'transaction',
        entity_types: ['DocumentReference', 'Task'],
      }),
    )
  if (today >= '2026-10-02')
    items.push(entry('2026-10-02T11:25:00+02:00', COORD, 'coordinator', {}))
  if (today >= '2026-10-20')
    items.push(
      entry('2026-10-20T09:15:00+02:00', PHYS, 'koc_physician', {
        entity_types: ['Task', 'Patient', 'EpisodeOfCare', 'DocumentReference'],
      }),
    )
  items.sort((a, b) => ms(b.recorded) - ms(a.recorded))
  return {
    case_id: ALENA_ID,
    items: items.slice(offset, offset + limit),
    total: items.length,
    offset,
    limit,
    truncated: offset + limit < items.length,
  }
}
