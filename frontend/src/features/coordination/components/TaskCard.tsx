import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { coordination as t } from '@/i18n/cs/coordination'
import { cn } from '@/lib/cn'
import { daysUntil, formatDate, formatRemaining } from '@/lib/date'
import { useResultDocuments, type BoardTask, type TransitionInput } from '../api'

type Action = 'confirm' | 'perform' | 'deliver'

/** The one step a task can take next, from the API's business status (`objednano` is "planned, not yet ordered"). */
function nextAction(task: BoardTask): Action | null {
  if (task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') return null
  switch (task.business_status ?? 'objednano') {
    case 'objednano':
      return 'confirm'
    case 'potvrzeno':
      return 'perform'
    case 'provedeno':
      return 'deliver'
    default:
      return null
  }
}

interface Props {
  task: BoardTask
  /** Titles by task id, to name what a blocked task waits for. */
  titles: Record<string, string>
  /** The API clock of the board; the countdown is measured from it. */
  now: string
  caseId: string
  canAct: boolean
  busy: boolean
  onTransition: (input: TransitionInput, done: () => void) => void
}

function ConfirmForm({ task, busy, onSubmit, onCancel }: { task: BoardTask; busy: boolean; onSubmit: (place: string, date: string) => void; onCancel: () => void }) {
  const [place, setPlace] = useState(task.place ?? '')
  const [date, setDate] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (place.trim() && date) onSubmit(place.trim(), date)
  }
  return (
    <form onSubmit={submit} aria-label={t.actions.aria(t.actions.confirm, task.title)} className="space-y-2 rounded border border-hairline bg-accent-soft/40 p-2">
      <p className="text-xs text-muted">{t.confirmForm.hint}</p>
      <label className="block text-xs font-medium">
        {t.confirmForm.place}
        <input required value={place} onChange={(e) => setPlace(e.target.value)} className="mt-1 block w-full rounded border border-hairline bg-card px-2 py-1 text-sm" />
      </label>
      <label className="block text-xs font-medium">
        {t.confirmForm.date}
        <input required type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 block w-full rounded border border-hairline bg-card px-2 py-1 text-sm" />
      </label>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" className="min-h-9 px-3 text-sm" disabled={busy || !place.trim() || !date}>
          {t.confirmForm.submit}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t.confirmForm.cancel}
        </Button>
      </div>
    </form>
  )
}

function DeliverForm({ task, caseId, busy, onSubmit, onCancel }: { task: BoardTask; caseId: string; busy: boolean; onSubmit: (documentId: string) => void; onCancel: () => void }) {
  const docs = useResultDocuments(caseId, true)
  const [documentId, setDocumentId] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (documentId) onSubmit(documentId)
  }
  const empty = docs.isSuccess && docs.data.documents.length === 0
  return (
    <form onSubmit={submit} aria-label={t.actions.aria(t.actions.deliver, task.title)} className="space-y-2 rounded border border-hairline bg-accent-soft/40 p-2">
      <p className="text-xs text-muted">{empty ? t.deliverForm.noDocuments : t.deliverForm.hint}</p>
      <label className="block text-xs font-medium">
        {t.deliverForm.document}
        <select required value={documentId} onChange={(e) => setDocumentId(e.target.value)} className="mt-1 block w-full rounded border border-hairline bg-card px-2 py-1 text-sm">
          <option value="">{t.deliverForm.choose}</option>
          {docs.data?.documents.map((d) => (
            <option key={d.doc_id} value={d.doc_id}>
              {d.title}
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <Button type="submit" variant="primary" className="min-h-9 px-3 text-sm" disabled={busy || !documentId}>
          {t.deliverForm.submit}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          {t.deliverForm.cancel}
        </Button>
      </div>
    </form>
  )
}

export function TaskCard({ task, titles, now, caseId, canAct, busy, onTransition }: Props) {
  const [form, setForm] = useState<'confirm' | 'deliver' | null>(null)
  const action = nextAction(task)
  const blockers = task.blocked_by.map((id) => titles[id] ?? id)
  const finished = task.status === 'completed' || task.business_status === 'vysledek_dorucen'
  const close = () => setForm(null)
  const label = action ? t.actions[action] : ''
  const click = () => {
    if (action === 'perform') onTransition({ taskId: task.id, event: 'perform' }, close)
    else setForm(action === 'confirm' ? 'confirm' : 'deliver')
  }
  const failedOrCancelled = task.status === 'failed' || task.status === 'cancelled' ? task.status : null

  return (
    <li className={cn('space-y-1.5 rounded border bg-card p-3 text-sm', task.overdue ? 'border-missing/60' : 'border-hairline')}>
      <p className="font-medium">{task.title}</p>
      <p className="text-muted">
        {t.task.place}: {task.place ?? t.task.placeUnknown}
      </p>
      {task.due && (
        <p className={cn(task.overdue && 'font-semibold text-missing')}>
          {t.task.due} {formatDate(task.due)}
          {!finished && ` (${formatRemaining(daysUntil(task.due, now))})`}
        </p>
      )}
      {task.sla_due && !finished && (
        <p className="text-xs text-muted">
          {t.task.sla} {formatDate(task.sla_due)}
        </p>
      )}
      {task.scheduled_at && (
        <p className="text-xs">
          {t.task.scheduled} {formatDate(task.scheduled_at)}
        </p>
      )}
      <div className="flex flex-wrap gap-1.5 text-xs">
        {task.overdue && <span className="rounded bg-missing-bg px-1.5 py-0.5 font-semibold text-missing">{t.task.overdue(task.overdue_workdays)}</span>}
        {task.escalated_at && <span className="rounded bg-missing-bg px-1.5 py-0.5 font-semibold text-missing">{t.task.escalated(formatDate(task.escalated_at))}</span>}
        {failedOrCancelled && <span className="rounded bg-missing-bg px-1.5 py-0.5">{t.task.status[failedOrCancelled]}</span>}
      </div>
      <p className="text-xs font-medium text-accent">{t.task.businessStatus[task.business_status ?? 'objednano']}</p>
      {task.recorded_on_behalf_by && <p className="text-xs text-muted">{t.task.onBehalf(task.recorded_on_behalf_by.display)}</p>}
      {task.result_doc_id && <p className="text-xs text-muted">{t.task.result(task.result_doc_id)}</p>}
      {blockers.length > 0 && <p className="text-xs text-conflict">{t.task.blockedBy(blockers.join(', '))}</p>}
      {action && form === null && (
        <Button variant="secondary" disabled={!canAct || busy || blockers.length > 0} onClick={click} aria-label={t.actions.aria(label, task.title)}>
          {label}
        </Button>
      )}
      {form === 'confirm' && (
        <ConfirmForm task={task} busy={busy} onCancel={close} onSubmit={(place, date) => onTransition({ taskId: task.id, event: 'confirm', place, date }, close)} />
      )}
      {form === 'deliver' && (
        <DeliverForm task={task} caseId={caseId} busy={busy} onCancel={close} onSubmit={(documentId) => onTransition({ taskId: task.id, event: 'deliver_result', documentId }, close)} />
      )}
    </li>
  )
}
