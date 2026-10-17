import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { mdt as t } from '@/i18n/cs/mdt'
import { ApiProblem } from '@/lib/api/problem'
import { formatDateTime } from '@/lib/date'
import type { Role } from '@/lib/domain'
import { problemText, useLoopEvent } from './api'

/**
 * Coordinator steps after the MDT: hand the signed conclusion to the GP, then close the case. `gpOpenedAt` is the
 * API's recorded opening by the GP; `null` means no opening is recorded, which is not proof the GP has not read it.
 */
export function LoopActions({
  caseId,
  state,
  role,
  gpOpenedAt,
}: {
  caseId: string
  state: string | undefined
  role: Role
  gpOpenedAt: string | null
}) {
  const send = useLoopEvent(caseId)
  const close = useLoopEvent(caseId)
  const [confirming, setConfirming] = useState(false)
  if (role !== 'coordinator') return null
  if (state !== 'zaver_mdt' && state !== 'zpetna_vazba_odeslana' && state !== 'uzavreno' && state !== 'pripraveno_mdt') return null

  // 503: the mail relay refused, nothing changed, so the same button simply tries again.
  const retry = send.error instanceof ApiProblem && send.error.status === 503

  return (
    <section aria-labelledby="loop-h" className="space-y-2 rounded-lg border border-hairline bg-card p-4">
      <h3 id="loop-h" className="text-xl">
        {t.loop.title}
      </h3>
      {state === 'pripraveno_mdt' && <p className="text-sm text-muted">{t.loop.waiting}</p>}
      {state === 'zaver_mdt' && (
        <>
          <p className="text-sm text-muted">{t.loop.sendHint}</p>
          <Button variant="primary" disabled={send.isPending} onClick={() => send.mutate({ event: 'send_feedback' })}>
            {send.isPending ? t.loop.sending : t.loop.send}
          </Button>
          {send.isError && (
            <p role="alert" className="text-sm text-missing">
              {retry ? t.loop.sendRetry : `${t.loop.sendError} ${problemText(send.error)}`}
            </p>
          )}
        </>
      )}
      {state === 'zpetna_vazba_odeslana' && (
        <>
          <p role="status" className="font-medium text-verified">
            {t.loop.handedOver}
          </p>
          <p className="text-sm">{gpOpenedAt ? t.loop.gpOpened(formatDateTime(gpOpenedAt)) : t.loop.gpNotOpened}</p>
          {!confirming ? (
            <Button variant="secondary" onClick={() => setConfirming(true)}>
              {t.loop.close}
            </Button>
          ) : (
            <div role="group" aria-label={t.loop.close} className="space-y-2 rounded border border-conflict/40 bg-conflict-bg p-3">
              {!gpOpenedAt && <p className="text-sm">{t.loop.closeWarning}</p>}
              <div className="flex gap-2">
                <Button variant="primary" className="min-h-9 px-3 text-sm" disabled={close.isPending} onClick={() => close.mutate({ event: 'close' })}>
                  {close.isPending ? t.loop.closing : gpOpenedAt ? t.loop.closeConfirmOpened : t.loop.closeConfirm}
                </Button>
                <Button variant="ghost" onClick={() => setConfirming(false)}>
                  {t.loop.closeCancel}
                </Button>
              </div>
              {close.isError && (
                <p role="alert" className="text-sm text-missing">
                  {t.loop.closeError} {problemText(close.error)}
                </p>
              )}
            </div>
          )}
        </>
      )}
      {state === 'uzavreno' && <p role="status">{t.loop.closed}</p>}
    </section>
  )
}
