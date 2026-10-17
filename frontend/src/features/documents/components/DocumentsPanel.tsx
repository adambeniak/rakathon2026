import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill } from '@/components/StatusPill'
import { cases as t } from '@/i18n/cs/cases'
import { formatDate } from '@/lib/date'
import { useDocuments } from '../api'
import { DocumentUpload } from './DocumentUpload'

const th = 'px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted'
const td = 'px-3 py-2 align-top'

/** The case's document list (moved from the Dokumenty tab); step 3 upload and per-document status build on it. */
export function DocumentsPanel({ caseId }: { caseId: string }) {
  const q = useDocuments(caseId)
  return (
    <section aria-label={t.documents.title} className="space-y-3">
      <h2 className="text-2xl">{t.documents.title}</h2>
      <DocumentUpload caseId={caseId} />
      {q.isPending && <LoadingBlock />}
      {q.isError && <ErrorState onRetry={() => void q.refetch()} />}
      {q.data && q.data.length === 0 && <EmptyState title={t.documents.empty} hint={t.documents.emptyHint} />}
      {q.data && q.data.length > 0 && (
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
            {q.data.map((d) => (
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
    </section>
  )
}
