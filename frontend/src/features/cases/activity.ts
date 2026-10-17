// Czech labels for the case activity the API returns as codes (timeline kinds, workflow events, audit operations).
// Data fields (document titles, step titles, request labels) are shown as the API returns them.
import type { TimelineItem } from '@/components/Timeline'
import { cases as t } from '@/i18n/cs/cases'
import { common } from '@/i18n/cs/common'
import type { AuditItem, TimelineEntry } from './schemas'

type EventCode = Exclude<keyof typeof t.events, 'other'>

/** Czech name of a workflow event code (`accept`, `send_feedback`, …); unknown codes are named with their code. */
export function eventLabel(code: string): string {
  return code in t.events && code !== 'other' ? t.events[code as EventCode] : t.events.other(code)
}

function stateLabel(state: string): string {
  return state in common.caseStates
    ? common.caseStates[state as keyof typeof common.caseStates]
    : state
}

function entryLabel(e: TimelineEntry): string {
  const title = e.title ?? t.timeline.untitled
  switch (e.kind) {
    case 'case_event':
      return eventLabel(e.event ?? '')
    case 'document_authored':
    case 'document_received':
    case 'request_sent':
    case 'request_fulfilled':
    case 'step_scheduled':
    case 'step_result_delivered':
    case 'step_escalated':
    case 'step_cancelled':
      return t.timeline.kinds[e.kind](title)
    default:
      return t.timeline.kinds[e.kind]
  }
}

export function timelineItem(e: TimelineEntry): TimelineItem {
  const notes: string[] = []
  if (e.from_state && e.to_state)
    notes.push(t.timeline.stateChange(stateLabel(e.from_state), stateLabel(e.to_state)))
  if (e.place) notes.push(e.place)
  if (e.actor) notes.push(`${t.timeline.by}: ${e.actor}`)
  if (e.receipt_id) notes.push(t.timeline.receipt(e.receipt_id))
  return {
    id: e.id,
    at: e.at,
    dateOnly: e.date_only,
    label: entryLabel(e),
    notes,
    excluded: e.excluded_from_handover === true, // null = no MDT start: nothing is flagged
    excludedLabel: t.timeline.afterAsOf,
    planned: e.planned,
    plannedLabel: t.timeline.planned,
  }
}

export function auditOperationLabel(item: AuditItem): string {
  if (item.workflow_event) return eventLabel(item.operation)
  return t.audit.operations[item.operation] ?? item.operation
}

export function auditEntities(item: AuditItem): string {
  return item.entity_types.map((type) => t.audit.entities[type] ?? type).join(', ')
}

export function auditActor(item: AuditItem): string {
  const who = item.actor ?? t.audit.unknownActor
  const role =
    item.actor_role && item.actor_role !== 'system' ? t.audit.roles[item.actor_role] : null
  return role ? `${who} (${role})` : who
}
