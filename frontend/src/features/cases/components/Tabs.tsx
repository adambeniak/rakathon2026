import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill } from '@/components/StatusPill'
import { Timeline } from '@/components/Timeline'
import { cases as t } from '@/i18n/cs/cases'
import { formatDate, formatDateTime } from '@/lib/date'
import { useAudit, useDocuments, useMessages, useTasks, useTimeline } from '../api'

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

const th = 'px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted'
const td = 'px-3 py-2 align-top'

export function DocumentsTab() {
  const { id = '' } = useParams()
  return (
    <Section title={t.documents.title} q={useDocuments(id)} empty={t.documents.empty} hint={t.documents.emptyHint}>
      {(docs) => (
        <table className="w-full border-collapse overflow-hidden rounded-lg border border-hairline bg-card">
          <thead className="border-b border-hairline">
            <tr>
              <th className={th}>{t.documents.cols.doc}</th>
              <th className={th}>{t.documents.cols.place}</th>
              <th className={th}>{t.documents.cols.authored}</th>
              <th className={th}>{t.documents.cols.received}</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id} className="border-b border-hairline last:border-0">
                <td className={td}>
                  <span className="font-mono text-xs text-muted">{d.id.slice(0, 2)}</span> {d.title}
                  {d.afterAsOf && <StatusPill kind="excluded" className="ml-2" />}
                </td>
                <td className={td}>{d.place}</td>
                <td className={td}>{formatDate(d.authored)}</td>
                <td className={td}>{formatDate(d.received)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  )
}

export function TasksTab() {
  const { id = '' } = useParams()
  const titleOf = (all: { id: string; title: string }[], dep: string) => all.find((x) => x.id === dep)?.title ?? dep
  return (
    <Section title={t.tasks.title} q={useTasks(id)} empty={t.tasks.empty} hint={t.tasks.emptyHint}>
      {(items) => (
        <table className="w-full border-collapse overflow-hidden rounded-lg border border-hairline bg-card">
          <thead className="border-b border-hairline">
            <tr>
              {Object.values(t.tasks.cols).map((c) => (
                <th key={c} className={th}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((x) => (
              <tr key={x.id} className="border-b border-hairline last:border-0">
                <td className={`${td} font-medium`}>{x.title}</td>
                <td className={td}>{x.owner}</td>
                <td className={td}>{x.place}</td>
                <td className={td}>{formatDate(x.due)}</td>
                <td className={td}>{x.dependsOn.length ? x.dependsOn.map((d) => titleOf(items, d)).join(', ') : t.tasks.none}</td>
                <td className={`${td} ${x.state === 'overdue' ? 'font-semibold text-missing' : ''}`}>{t.tasks.state[x.state]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  )
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
