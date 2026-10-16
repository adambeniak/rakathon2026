import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Timeline } from '@/components/Timeline'
import { cases as t } from '@/i18n/cs/cases'
import { formatDateTime } from '@/lib/date'
import { DocumentsPanel } from '@/features/documents/components/DocumentsPanel'
import { useAudit, useMessages, useTimeline } from '../api'

type Q<T> = { isPending: boolean; isError: boolean; data?: T; refetch: () => unknown }

function Section<T>({ title, q, empty, hint, children }: { title: string; q: Q<T[]>; empty: string; hint: string; children: (d: T[]) => ReactNode }) {
  return (
    <section aria-label={title} className="space-y-3">
      <h2 className="text-2xl">{title}</h2>
      {q.isPending && <LoadingBlock />}
      {q.isError && <ErrorState onRetry={() => void q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title={empty} hint={hint} />}
      {q.data && q.data.length > 0 && children(q.data)}
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
    <Section title={t.timeline.title} q={useTimeline(id)} empty={t.timeline.empty} hint={t.timeline.emptyHint}>
      {(events) => <Timeline events={events} />}
    </Section>
  )
}

export function MessagesTab() {
  const { id = '' } = useParams()
  return (
    <Section title={t.messages.title} q={useMessages(id)} empty={t.messages.empty} hint={t.messages.emptyHint}>
      {(msgs) => (
        <ul className="space-y-3">
          {msgs.map((m) => (
            <li key={m.id} className="rounded-lg border border-hairline bg-card p-4">
              <p className="font-medium">{m.subject}</p>
              <p className="text-xs text-muted">
                {t.messages.from}: {m.from} · {t.messages.to}: {m.to} · {formatDateTime(m.at)}
              </p>
              <p className="mt-1">{m.body}</p>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}

export function AuditTab() {
  const { id = '' } = useParams()
  return (
    <Section title={t.audit.title} q={useAudit(id)} empty={t.audit.empty} hint={t.audit.emptyHint}>
      {(rows) => (
        <ul className="divide-y divide-hairline rounded-lg border border-hairline bg-card">
          {rows.map((r) => (
            <li key={`${r.at}-${r.action}`} className="flex gap-4 px-4 py-2">
              <span className="w-40 shrink-0 font-mono text-xs text-muted">{formatDateTime(r.at)}</span>
              <span className="w-36 shrink-0 font-medium">{r.who}</span>
              <span>{r.action}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )
}
