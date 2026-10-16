import { CaseStateBadge } from '@/components/CaseStateBadge'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { reviewer as t } from '@/i18n/cs/reviewer'
import { cases } from '@/i18n/cs/cases'
import { formatDate } from '@/lib/date'
import { useReviewerCases } from './api'

const initials = (name: string) =>
  name
    .split(' ')
    .map((p) => `${p[0] ?? ''}.`)
    .join(' ')

const days = (n: number | null) => (n === null ? t.pending : cases.header.days(n))

export function Reviewer() {
  const q = useReviewerCases()
  if (q.isPending) return <LoadingBlock lines={4} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />

  return (
    <div className="space-y-4">
      <h1 className="text-3xl">{t.title}</h1>
      <p className="text-muted">{t.hint}</p>
      {q.data.length === 0 ? (
        <EmptyState title={t.empty} hint={t.emptyHint} />
      ) : (
        <table className="w-full border-collapse overflow-hidden rounded-lg border border-hairline bg-card">
          <thead className="border-b border-hairline">
            <tr>
              {Object.values(t.cols).map((c) => (
                <th key={c} className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {q.data.map((c) => (
              <tr key={c.id} className="border-b border-hairline last:border-0">
                <td className="px-3 py-3">
                  {initials(c.patientName)}, {c.birthDate.slice(0, 4)}
                </td>
                <td className="px-3 py-3">{c.diagnosis.split(' – ')[0]}</td>
                <td className="px-3 py-3">
                  <CaseStateBadge state={c.state} />
                </td>
                <td className="px-3 py-3">{formatDate(c.referredAt)}</td>
                <td className="px-3 py-3 font-mono text-sm">{days(c.t.t1)}</td>
                <td className="px-3 py-3 font-mono text-sm">{days(c.t.t2)}</td>
                <td className="px-3 py-3 font-mono text-sm">{days(c.t.t3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
