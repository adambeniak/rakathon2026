import { CaseStateBadge } from '@/components/CaseStateBadge'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { intervalText } from '@/features/cases/intervals'
import { reviewer as t } from '@/i18n/cs/reviewer'
import { formatDate, formatDateTime } from '@/lib/date'
import { useReviewerCases, type ReviewerCase } from './api'

const cell = 'px-3 py-3 align-top'

function delivery(d: ReviewerCase['delivery']): string {
  if (d.status === 'opened_by_gp' && d.gp_opened_at)
    return t.openedOn(formatDateTime(d.gp_opened_at))
  return t.delivery[d.status]
}

export function Reviewer() {
  const q = useReviewerCases()
  if (q.isPending) return <LoadingBlock lines={4} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />

  const insurer = q.data[0]?.insurer_code
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-3xl">{t.title}</h1>
        {insurer && <p className="font-semibold">{t.insurer(insurer)}</p>}
      </div>
      <p className="max-w-3xl text-muted">{t.hint}</p>
      {q.data.length === 0 ? (
        <EmptyState title={t.empty} hint={t.emptyHint} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-hairline bg-card">
          <table className="w-full border-collapse">
            <caption className="sr-only">{t.caption}</caption>
            <thead className="border-b border-hairline">
              <tr>
                {Object.values(t.cols).map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {q.data.map((c) => (
                <tr key={c.ref} className="border-b border-hairline last:border-0">
                  <th scope="row" className={`${cell} text-left font-normal`}>
                    {c.initials}, {c.birth_year}
                  </th>
                  <td className={`${cell} font-mono text-xs`}>{c.ref}</td>
                  <td className={cell}>{c.diagnosis_group ?? t.pending}</td>
                  <td className={cell}>
                    <CaseStateBadge state={c.state} />
                  </td>
                  <td className={cell}>{c.referred_on ? formatDate(c.referred_on) : t.pending}</td>
                  <td className={`${cell} font-mono text-sm`}>{intervalText(c.intervals.t1)}</td>
                  <td className={`${cell} font-mono text-sm`}>{intervalText(c.intervals.t2)}</td>
                  <td className={`${cell} font-mono text-sm`}>{intervalText(c.intervals.t3)}</td>
                  <td className={cell}>{delivery(c.delivery)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="max-w-3xl text-xs text-muted">{t.proxies}</p>
    </div>
  )
}
