import { useState, type FormEvent } from 'react'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { mdt as t } from '@/i18n/cs/mdt'
import { formatDateTime } from '@/lib/date'
import type { Role } from '@/lib/domain'
import { problemText, useConclusion, useLoopEvent } from './api'

/**
 * The MDT conclusion. Only a signed conclusion (read back from `GET /mdt-conclusion`) is shown as saved; the
 * physician's form is offered while the case is `pripraveno_mdt` and nothing is signed yet.
 */
export function ConclusionPanel({ caseId, state, role }: { caseId: string; state: string | undefined; role: Role }) {
  const team = role === 'coordinator' || role === 'physician'
  const conclusion = useConclusion(caseId, team)
  const record = useLoopEvent(caseId)
  const [text, setText] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim()) record.mutate({ event: 'record_mdt_conclusion', conclusion: text })
  }
  const signed = conclusion.data

  return (
    <div className="border-t border-hairline pt-2">
      <p className="font-medium">{t.conclusionTitle}</p>
      {conclusion.isPending && team && <LoadingBlock lines={2} />}
      {conclusion.isError && (
        <p role="alert" className="text-sm text-missing">
          {t.conclusion.loadError} {problemText(conclusion.error)}
        </p>
      )}
      {signed && (
        <section aria-label={t.conclusion.signed} className="space-y-1 rounded border border-verified/40 bg-verified-bg p-3">
          <p className="whitespace-pre-wrap">{signed.text}</p>
          <p className="text-sm text-muted">{t.conclusion.signedBy(signed.signed_by.display, formatDateTime(signed.signed_at))}</p>
        </section>
      )}
      {signed === null && role === 'physician' && state === 'pripraveno_mdt' && !record.isSuccess && (
        <form onSubmit={submit} aria-label={t.conclusion.submit} className="space-y-2">
          <label className="block text-sm font-medium">
            {t.conclusion.label}
            <textarea
              required
              rows={5}
              maxLength={4000}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="mt-1 block w-full rounded border border-hairline bg-card px-3 py-2 text-sm"
            />
          </label>
          <p className="text-xs text-muted">{t.conclusion.hint}</p>
          {record.isError && (
            <p role="alert" className="text-sm text-missing">
              {t.conclusion.saveError} {problemText(record.error)}
            </p>
          )}
          <Button type="submit" variant="primary" disabled={record.isPending || !text.trim()}>
            {record.isPending ? t.conclusion.submitting : t.conclusion.submit}
          </Button>
        </form>
      )}
      {signed === null && record.isSuccess && <p role="status" className="text-sm text-muted">{t.conclusion.loadingSaved}</p>}
      {signed === null && !(role === 'physician' && state === 'pripraveno_mdt') && !record.isSuccess && (
        <p className="rounded border border-dashed border-hairline p-3 text-sm text-muted">{t.conclusionPlaceholder}</p>
      )}
    </div>
  )
}
