import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { mdt as t } from '@/i18n/cs/mdt'
import type { Role } from '@/lib/domain'
import { blockingItems, problemText, useLoopEvent } from './api'

const label = (item: string) => t.ready.items[item] ?? item

/**
 * Marks the case ready for the MDT (Lékař KOC, state `kompletni`). The gate is the server's: when it refuses, the
 * blocking items come from the response, and the physician may waive them with a reason and send the request again.
 */
export function MarkReady({ caseId, state, role }: { caseId: string; state: string | undefined; role: Role }) {
  const mark = useLoopEvent(caseId)
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [waiving, setWaiving] = useState(false)
  if (role !== 'physician') return null
  if (mark.isSuccess)
    return (
      <p role="status" className="rounded-lg border border-verified/40 bg-verified-bg p-3 text-verified">
        {t.ready.done}
      </p>
    )
  if (state !== 'kompletni') return null

  const blocking = blockingItems(mark.error)
  const showForm = waiving && blocking !== null
  const complete = blocking?.every((i) => (reasons[i] ?? '').trim()) ?? false
  const first = () => {
    setWaiving(true)
    mark.mutate({ event: 'mark_ready_mdt' })
  }
  const waive = (e: FormEvent) => {
    e.preventDefault()
    if (blocking && complete) mark.mutate({ event: 'mark_ready_mdt', waivers: blocking.map((item) => ({ item, reason: reasons[item] ?? '' })) })
  }

  return (
    <section aria-labelledby="ready-h" className="space-y-2 rounded-lg border border-hairline bg-card p-4">
      <h3 id="ready-h" className="text-xl">
        {t.ready.title}
      </h3>
      <p className="text-sm text-muted">{t.ready.hint}</p>
      {!showForm && (
        <Button variant="primary" disabled={mark.isPending} onClick={first}>
          {mark.isPending ? t.ready.acting : t.ready.action}
        </Button>
      )}
      {mark.isError && blocking === null && (
        <p role="alert" className="text-sm text-missing">
          {t.ready.error} {problemText(mark.error)}
        </p>
      )}
      {showForm && (
        <form onSubmit={waive} aria-label={t.ready.waive} className="space-y-3 rounded border border-conflict/40 bg-conflict-bg p-3">
          <p className="font-medium">{t.ready.blocked}</p>
          <p className="text-sm">{t.ready.blockedHint}</p>
          {blocking.map((item) => (
            <label key={item} className="block text-sm font-medium">
              {t.ready.reason(label(item))}
              <input
                required
                maxLength={500}
                value={reasons[item] ?? ''}
                onChange={(e) => setReasons({ ...reasons, [item]: e.target.value })}
                className="mt-1 block w-full rounded border border-hairline bg-card px-3 py-2 text-sm"
              />
            </label>
          ))}
          <div className="flex gap-2">
            <Button type="submit" variant="primary" className="min-h-9 px-3 text-sm" disabled={mark.isPending || !complete}>
              {mark.isPending ? t.ready.acting : t.ready.waive}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setWaiving(false)}>
              {t.ready.cancel}
            </Button>
          </div>
        </form>
      )}
    </section>
  )
}
