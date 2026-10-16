import { BadgeCheck, CircleAlert, Info, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill, pillForHandover } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api/http'
import { mdt as t } from '@/i18n/cs/mdt'
import { formatDate, formatDateTime, isoToPragueLocal, pragueLocalToIso } from '@/lib/date'
import { cn } from '@/lib/cn'
import { useGenerateMdt, useMdt } from './api'
import type { GateItem } from './types'

const AS_OF_DEFAULT = '2026-10-21T08:00:00+02:00'

const LEVEL = {
  ok: { Icon: BadgeCheck, cls: 'text-verified' },
  blocker: { Icon: CircleAlert, cls: 'text-missing' },
  warning: { Icon: TriangleAlert, cls: 'text-conflict' },
  info: { Icon: Info, cls: 'text-muted' },
} as const

function Gate({ items }: { items: GateItem[] }) {
  return (
    <ul className="space-y-2">
      {items.map((g) => {
        const { Icon, cls } = LEVEL[g.level]
        return (
          <li key={g.id} className="flex gap-2">
            <Icon aria-hidden className={cn('mt-0.5 h-4 w-4 shrink-0', cls)} />
            <div>
              <p>
                <span className={cn('mr-2 text-xs font-semibold', cls)}>{t.gateLevels[g.level]}</span>
                {g.label}
              </p>
              {g.detail && <p className="text-sm text-muted">{g.detail}</p>}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function Mdt() {
  const { id = '' } = useParams()
  const [asOf, setAsOf] = useState(AS_OF_DEFAULT)
  const q = useMdt(id, asOf)
  const gen = useGenerateMdt(id, asOf)

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl">{t.title}</h2>
          <label className="mt-2 flex flex-col text-sm">
            <span className="font-medium">{t.asOfLabel}</span>
            <input
              type="datetime-local"
              value={isoToPragueLocal(asOf)}
              onChange={(e) => e.target.value && setAsOf(pragueLocalToIso(e.target.value))}
              className="min-h-9 w-64 rounded border border-hairline bg-card px-2"
              aria-describedby="asof-hint"
            />
            <span id="asof-hint" className="text-xs text-muted">
              {t.asOfHint}
            </span>
          </label>
        </div>
        <div className="max-w-sm text-right">
          <Button
            variant="primary"
            disabled={!q.data?.ready || gen.isPending}
            aria-describedby="gate-h"
            onClick={() => gen.mutate()}
          >
            {t.generate}
          </Button>
          {q.data && !q.data.ready && <p className="mt-1 text-xs text-missing">{t.generateBlocked}</p>}
        </div>
      </div>

      {q.isPending && <LoadingBlock lines={6} />}
      {q.isError &&
        (q.error instanceof ApiError && q.error.status === 404 ? (
          <EmptyState title={t.notAvailable} hint={t.notAvailableHint} />
        ) : (
          <ErrorState onRetry={() => void q.refetch()} />
        ))}

      {q.data && (
        <>
          {(q.data.generatedAt || gen.isSuccess) && (
            <div role="status" className="rounded-lg border border-verified/40 bg-verified-bg p-3 text-verified">
              {t.generated(formatDateTime(q.data.generatedAt ?? asOf))} <span className="text-muted">{t.exportNote}</span>
            </div>
          )}
          <section aria-labelledby="gate-h" className="rounded-lg border border-hairline bg-card p-4">
            <h3 id="gate-h" className="mb-3 text-xl">
              {t.gateTitle}
            </h3>
            <Gate items={q.data.gate} />
          </section>

          <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
            <section aria-labelledby="rec-h" className="space-y-3 rounded-lg border border-hairline bg-card p-5">
              <h3 id="rec-h" className="text-xl">
                {t.recordTitle}
              </h3>
              <p className="text-sm text-muted">{t.recordHint}</p>
              {q.data.sections.map((s) => (
                <div key={s.key} className="border-t border-hairline pt-2">
                  <p className="flex flex-wrap items-center gap-2 font-medium">
                    <span className="font-mono text-xs text-muted">{s.number}</span>
                    {s.title}
                    {pillForHandover(s.status, s.confirmed).map((p) => (
                      <StatusPill key={p} kind={p} />
                    ))}
                  </p>
                  <ul className="mt-1 text-sm">
                    {s.rows.slice(0, 4).map((r, i) => (
                      <li key={i}>{r.label ? `${r.label}: ${r.value}` : r.value}</li>
                    ))}
                    {s.rows.length > 4 && <li className="text-muted">… {s.rows.length - 4}</li>}
                  </ul>
                </div>
              ))}
              <div className="border-t border-hairline pt-2">
                <p className="font-medium">{t.conclusionTitle}</p>
                <p className="rounded border border-dashed border-hairline p-3 text-sm text-muted">{t.conclusionPlaceholder}</p>
              </div>
            </section>

            <aside className="space-y-4">
              <section aria-labelledby="inc-h" className="rounded-lg border border-hairline bg-card p-4">
                <h3 id="inc-h" className="text-xl">
                  {t.includedTitle}
                </h3>
                <ul className="mt-2 space-y-1 text-sm">
                  {q.data.included.map((d) => (
                    <li key={d.id}>
                      <span className="font-mono text-xs text-muted">{d.id.slice(0, 2)}</span> {d.title}{' '}
                      <span className="text-muted">{formatDate(d.authored)}</span>
                    </li>
                  ))}
                </ul>
              </section>
              {q.data.excluded.length > 0 && (
                <section aria-labelledby="exc-h" className="rounded-lg border border-dashed border-hairline bg-stale-bg/40 p-4">
                  <h3 id="exc-h" className="text-xl">
                    {t.excludedTitle}
                  </h3>
                  <ul className="mt-2 space-y-1 text-sm">
                    {q.data.excluded.map((d) => (
                      <li key={d.id}>
                        <StatusPill kind="excluded" /> <span className="font-mono text-xs">{d.id.slice(0, 2)}</span> {d.title}{' '}
                        <span className="text-muted">{formatDate(d.authored)}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
