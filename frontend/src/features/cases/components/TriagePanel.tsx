import { Paperclip, Send } from 'lucide-react'
import { useState } from 'react'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { EvidenceChip } from '@/components/EvidenceChip'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { cases as t } from '@/i18n/cs/cases'
import { problemTitle } from '@/lib/api/problem'
import { formatDate } from '@/lib/date'
import { useCase, useDocumentRequests, useProposals, useRequestDocuments } from '../api'

/** Demo step 2: the reports the referral letter lists but nobody attached, as one checklist sent with a single click. */
export function TriagePanel({ caseId, canAct }: { caseId: string; canAct: boolean }) {
  const proposals = useProposals(caseId)
  const requests = useDocumentRequests(caseId)
  const send = useRequestDocuments(caseId)
  const documents = useCase(caseId).data?.documents
  const [unchecked, setUnchecked] = useState<Set<string>>(new Set())

  if (proposals.isPending || requests.isPending) return <LoadingBlock lines={3} />
  if (proposals.isError || requests.isError) {
    return <ErrorState onRetry={() => void Promise.all([proposals.refetch(), requests.refetch()])} />
  }
  if (proposals.data.proposals.length === 0) return <EmptyState title={t.triage.empty} hint={t.triage.emptyHint} />

  // A proposal is done when a request with its label exists; a missing workplace cannot be requested (the API needs it).
  const rows = proposals.data.proposals.map((p) => ({
    p,
    requested: requests.data.some((r) => r.label === p.label),
    selectable: p.status === 'missing' && !!p.recipient_org_id && !requests.data.some((r) => r.label === p.label),
  }))
  const selected = rows.filter((r) => r.selectable && !unchecked.has(r.p.key))
  const toggle = (key: string) =>
    setUnchecked((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })

  return (
    <section id="triage" aria-labelledby="triage-h" className="space-y-3 rounded-lg border border-hairline bg-card p-4">
      <div>
        <div className="flex items-center gap-2">
          <h2 id="triage-h" className="text-xl">
            {t.triage.title}
          </h2>
          <StatusPill kind="ai" />
        </div>
        <p className="text-sm text-muted">{t.triage.hint}</p>
        <p className="text-sm font-medium">{t.triage.proposal}</p>
      </div>
      <ul className="divide-y divide-hairline">
        {rows.map(({ p, requested, selectable }) => (
          <li key={p.key} className="py-2">
            <div className="flex items-start gap-3">
              <input
                id={`req-${p.key}`}
                type="checkbox"
                className="mt-1 h-4 w-4 accent-[var(--accent)]"
                checked={requested || (selectable && !unchecked.has(p.key))}
                disabled={!selectable || !canAct}
                aria-describedby={`req-${p.key}-to`}
                onChange={() => toggle(p.key)}
              />
              <div className="min-w-0 flex-1">
                {/* Only the label text is the checkbox name; the chips are buttons and stay outside the label. */}
                <label htmlFor={`req-${p.key}`} className="block font-medium">
                  {p.label}
                </label>
                <span id={`req-${p.key}-to`} className="block text-sm text-muted">
                  {t.triage.recipient}: {p.recipient_name ?? t.triage.noRecipient}
                  {p.exam_date && ` · ${formatDate(p.exam_date)}`}
                </span>
                <span className="mt-1 flex flex-wrap gap-2">
                  {p.evidence.map((e) => (
                    <EvidenceChip key={e.quote} docId={e.doc_id} quote={e.quote} doc={documents?.find((d) => d.id === e.doc_id)} />
                  ))}
                </span>
              </div>
              {(requested || p.status !== 'missing') && (
                <span className="inline-flex items-center gap-1 whitespace-nowrap text-sm font-medium text-ink">
                  {requested ? <Send aria-hidden className="h-3.5 w-3.5" /> : <Paperclip aria-hidden className="h-3.5 w-3.5" />}
                  {requested ? t.triage.requested : t.triage.attached}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-3">
        <Button
          variant="primary"
          disabled={!canAct || selected.length === 0 || send.isPending}
          onClick={() =>
            send.mutate(
              selected.flatMap(({ p }) =>
                p.recipient_org_id ? [{ label: p.label, recipient_org_id: p.recipient_org_id, exam_date: p.exam_date }] : [],
              ),
            )
          }
        >
          {send.isPending ? t.triage.submitting : t.triage.submit}
        </Button>
        {send.isSuccess && selected.length === 0 && (
          <span role="status" className="text-sm text-verified">
            {t.triage.done(requests.data.length)}
          </span>
        )}
        {send.isError && (
          <span role="alert" className="text-sm text-missing">
            {t.triage.error} {problemTitle(send.error)}
          </span>
        )}
      </div>
    </section>
  )
}
