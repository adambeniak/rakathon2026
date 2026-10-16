import { useState } from 'react'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { cases as t } from '@/i18n/cs/cases'
import { useDocumentRequests, useRequestDocuments } from '../api'

/** Demo step 2: proposed document requests as one checklist, sent with a single click. */
export function TriagePanel({ caseId, canAct }: { caseId: string; canAct: boolean }) {
  const q = useDocumentRequests(caseId)
  const send = useRequestDocuments(caseId)
  const [unchecked, setUnchecked] = useState<Set<string>>(new Set())

  if (q.isPending) return <LoadingBlock lines={3} />
  if (q.isError) return <ErrorState onRetry={() => void q.refetch()} />
  if (q.data.length === 0) return <EmptyState title={t.triage.empty} hint={t.triage.emptyHint} />

  const open = q.data.filter((r) => !r.requested)
  const selected = open.filter((r) => !unchecked.has(r.id))
  const toggle = (id: string) =>
    setUnchecked((prev) => {
      const next = new Set(prev)
      if (!next.delete(id)) next.add(id)
      return next
    })

  return (
    <section id="triage" aria-labelledby="triage-h" className="space-y-3 rounded-lg border border-hairline bg-card p-4">
      <div>
        <h2 id="triage-h" className="text-xl">
          {t.triage.title}
        </h2>
        <p className="text-sm text-muted">{t.triage.hint}</p>
        <p className="text-sm font-medium">{t.triage.proposal}</p>
      </div>
      <ul className="divide-y divide-hairline">
        {q.data.map((r) => (
          <li key={r.id} className="py-2">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-[var(--accent)]"
                checked={r.requested || !unchecked.has(r.id)}
                disabled={r.requested || !canAct}
                onChange={() => toggle(r.id)}
              />
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{r.title}</span>
                <span className="block text-sm text-muted">
                  {t.triage.recipient}: {r.recipient}
                </span>
              </span>
              {r.requested && <span className="text-sm font-medium text-verified">{t.triage.requested}</span>}
            </label>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-3">
        <Button
          variant="primary"
          disabled={!canAct || selected.length === 0 || send.isPending}
          onClick={() => send.mutate(selected.map((r) => r.id))}
        >
          {send.isPending ? t.triage.submitting : t.triage.submit}
        </Button>
        {send.isSuccess && open.length === 0 && (
          <span role="status" className="text-sm text-verified">
            {t.triage.done(q.data.length)}
          </span>
        )}
        {send.isError && (
          <span role="alert" className="text-sm text-missing">
            {t.triage.error}
          </span>
        )}
      </div>
    </section>
  )
}
