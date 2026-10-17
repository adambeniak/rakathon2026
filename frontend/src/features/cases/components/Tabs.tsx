import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Timeline } from '@/components/Timeline'
import { cases as t } from '@/i18n/cs/cases'
import { formatDate, formatDateTime } from '@/lib/date'
import { DocumentsPanel } from '@/features/documents/components/DocumentsPanel'
import { auditActor, auditEntities, auditOperationLabel, timelineItem } from '../activity'
import { useAudit, useMessages, useTimeline } from '../api'
import type { CaseMessage } from '../schemas'

type Q<T> = { isPending: boolean; isError: boolean; data?: T; refetch: () => unknown }

function Section<T>({
  title,
  q,
  items,
  empty,
  hint,
  children,
}: {
  title: string
  q: Q<T>
  items: (data: T) => readonly unknown[]
  empty: string
  hint: string
  children: (d: T) => ReactNode
}) {
  return (
    <section aria-label={title} className="space-y-3">
      <h2 className="text-2xl">{title}</h2>
      {q.isPending && <LoadingBlock />}
      {q.isError && <ErrorState onRetry={() => void q.refetch()} />}
      {q.data && items(q.data).length === 0 && <EmptyState title={empty} hint={hint} />}
      {q.data && items(q.data).length > 0 && children(q.data)}
    </section>
  )
}

export function DocumentsTab() {
  const { id = '' } = useParams()
  return <DocumentsPanel caseId={id} />
}

export function TimelineTab() {
  const { id = '' } = useParams()
  return (
    <Section
      title={t.timeline.title}
      q={useTimeline(id)}
      items={(d) => d.events}
      empty={t.timeline.empty}
      hint={t.timeline.emptyHint}
    >
      {(timeline) => (
        <>
          {timeline.as_of && (
            <p className="text-sm text-muted">{t.timeline.asOf(formatDateTime(timeline.as_of))}</p>
          )}
          <Timeline events={timeline.events.map(timelineItem)} />
        </>
      )}
    </Section>
  )
}

function MessageCard({ m }: { m: CaseMessage }) {
  return (
    <li className="rounded-lg border border-hairline bg-card p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">{t.messages.kinds[m.kind]}</p>
        <span className="rounded-full border border-hairline px-2 py-0.5 text-xs">
          {t.messages.status[m.status]}
        </span>
      </div>
      <p className="text-xs text-muted">
        {t.messages.from}: {m.sender ?? '—'} · {t.messages.to}: {m.recipient ?? '—'}
        {m.sent_at && (
          <>
            {' '}
            · {t.messages.sentAt}: {formatDateTime(m.sent_at)}
          </>
        )}
      </p>
      <p className="mt-2 whitespace-pre-line">{m.text}</p>
      {m.request && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 text-xs text-muted">
          {m.request.due && (
            <>
              <dt>{t.messages.due}</dt>
              <dd>{formatDate(m.request.due)}</dd>
            </>
          )}
          {m.request.result_doc_id && (
            <>
              <dt>{t.messages.result}</dt>
              <dd className="font-mono">{m.request.result_doc_id}</dd>
            </>
          )}
        </dl>
      )}
      {m.delivery && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 text-xs text-muted">
          {m.delivery.receipt_id && (
            <>
              <dt>{t.messages.receipt}</dt>
              <dd className="font-mono break-all">{m.delivery.receipt_id}</dd>
            </>
          )}
          <dt>{t.messages.gpOpened}</dt>
          <dd>
            {m.delivery.gp_opened_at
              ? formatDateTime(m.delivery.gp_opened_at)
              : t.messages.gpNotOpened}
          </dd>
          <dd className="col-span-2">{t.messages.receiptNote}</dd>
        </dl>
      )}
    </li>
  )
}

export function MessagesTab() {
  const { id = '' } = useParams()
  return (
    <Section
      title={t.messages.title}
      q={useMessages(id)}
      items={(d) => d}
      empty={t.messages.empty}
      hint={t.messages.emptyHint}
    >
      {(msgs) => (
        <ul className="space-y-3">
          {msgs.map((m) => (
            <MessageCard key={m.id} m={m} />
          ))}
        </ul>
      )}
    </Section>
  )
}

export function AuditTab() {
  const { id = '' } = useParams()
  return (
    <Section
      title={t.audit.title}
      q={useAudit(id)}
      items={(d) => d.items}
      empty={t.audit.empty}
      hint={t.audit.emptyHint}
    >
      {(trail) => (
        <>
          <table className="w-full rounded-lg border border-hairline bg-card text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th scope="col" className="px-4 py-2 font-normal">
                  {t.audit.cols.at}
                </th>
                <th scope="col" className="px-4 py-2 font-normal">
                  {t.audit.cols.who}
                </th>
                <th scope="col" className="px-4 py-2 font-normal">
                  {t.audit.cols.action}
                </th>
                <th scope="col" className="px-4 py-2 font-normal">
                  {t.audit.cols.records}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {trail.items.map((r, i) => (
                <tr key={`${r.recorded}-${i}`}>
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-muted">
                    {formatDateTime(r.recorded)}
                  </td>
                  <td className="px-4 py-2">
                    {auditActor(r)}
                    {r.on_behalf_of && (
                      <span className="block text-xs text-muted">
                        {t.audit.onBehalfOf(r.on_behalf_of)}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2 font-medium">
                    {auditOperationLabel(r)}
                    {r.outcome === 'failure' && (
                      <span className="ml-1 text-xs text-missing">({t.audit.failed})</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">{auditEntities(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {trail.truncated && (
            <p className="text-xs text-muted">{t.audit.shown(trail.items.length, trail.total)}</p>
          )}
        </>
      )}
    </Section>
  )
}
