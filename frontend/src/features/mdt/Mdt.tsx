import { useParams } from 'react-router-dom'
import { useDemo } from '@/app/DemoContext'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { EvidenceChip } from '@/components/EvidenceChip'
import { LoadingBlock } from '@/components/Skeleton'
import { StatusPill, pillForHandover } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { useCase } from '@/features/cases/api'
import { useHandover } from '@/features/handover/api'
import type { HandoverView, SectionView } from '@/features/handover/types'
import { mdt as t } from '@/i18n/cs/mdt'
import { ApiProblem } from '@/lib/api/problem'
import { formatDate, formatDateTime } from '@/lib/date'
import type { DocumentInfo } from '@/lib/domain'
import { mdtRecordFileName, problemTitle, useDownloadMdtRecord } from './api'

type CountKey = keyof typeof t.summaryCounts
const COUNT_KEYS = Object.keys(t.summaryCounts) as CountKey[]

/** Status counts straight from the API's section statuses; the UI decides nothing about readiness. */
function summarize(sections: SectionView[]) {
  const counts = COUNT_KEYS.map((key) => ({ key, n: sections.filter((s) => s.status === key).length })).filter((c) => c.n > 0)
  return { confirmed: sections.filter((s) => s.confirmed).length, counts }
}

/** Findings of all sections, each once, with the sections that cite it. */
function collectFindings(sections: SectionView[]) {
  const byId = new Map<string, { id: string; message: string; evidence: SectionView['findings'][number]['evidence']; sections: string[] }>()
  for (const s of sections)
    for (const f of s.findings) {
      const known = byId.get(f.id)
      if (known) known.sections.push(s.title)
      else byId.set(f.id, { ...f, sections: [s.title] })
    }
  return [...byId.values()]
}

function Summary({ sections }: { sections: SectionView[] }) {
  const { confirmed, counts } = summarize(sections)
  return (
    <section aria-labelledby="sum-h" className="space-y-2 rounded-lg border border-hairline bg-card p-4">
      <h3 id="sum-h" className="text-xl">
        {t.summaryTitle}
      </h3>
      <p>{t.summaryConfirmed(confirmed, sections.length)}</p>
      {counts.length > 0 && (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
          {counts.map((c) => (
            <li key={c.key}>
              {t.summaryCounts[c.key]}: <strong>{c.n}</strong>
            </li>
          ))}
        </ul>
      )}
      <p className="text-sm text-muted">{t.summaryHint}</p>
    </section>
  )
}

function Findings({ sections, docs }: { sections: SectionView[]; docs: Map<string, DocumentInfo> }) {
  const findings = collectFindings(sections)
  return (
    <section aria-labelledby="find-h" className="space-y-2 rounded-lg border border-hairline bg-card p-4">
      <h3 id="find-h" className="text-xl">
        {t.findingsTitle}
      </h3>
      {findings.length === 0 && <p className="text-sm text-muted">{t.findingsNone}</p>}
      <ul className="space-y-3">
        {findings.map((f) => (
          <li key={f.id} className="text-sm">
            <p>
              <span className="mr-2 font-mono text-xs text-muted">{f.id}</span>
              {f.message}
            </p>
            <p className="text-xs text-muted">{t.findingSections(f.sections.join(', '))}</p>
            {f.evidence.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {f.evidence.map((e, i) => (
                  <EvidenceChip key={`${e.docId}-${i}`} docId={e.docId} quote={e.quote} doc={docs.get(e.docId)} />
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

function Record({ view, docs }: { view: HandoverView; docs: Map<string, DocumentInfo> }) {
  return (
    <section aria-labelledby="rec-h" className="space-y-3 rounded-lg border border-hairline bg-card p-5">
      <h3 id="rec-h" className="text-xl">
        {t.recordTitle}
      </h3>
      <p className="text-sm text-muted">{t.recordHint}</p>
      {view.sections.map((s) => (
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
          {s.evidence.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {s.evidence.map((e, i) => (
                <EvidenceChip key={`${e.docId}-${i}`} docId={e.docId} quote={e.quote} doc={docs.get(e.docId)} />
              ))}
            </div>
          )}
        </div>
      ))}
      <div className="border-t border-hairline pt-2">
        <p className="font-medium">{t.conclusionTitle}</p>
        <p className="rounded border border-dashed border-hairline p-3 text-sm text-muted">{t.conclusionPlaceholder}</p>
      </div>
    </section>
  )
}

/** Demo step 5: the case as of the MDT start. As-of and the excluded reports are the API's, never computed here. */
export function Mdt() {
  const { id = '' } = useParams()
  const { role } = useDemo()
  const q = useHandover(id)
  const c = useCase(id)
  const download = useDownloadMdtRecord(id)
  const docs = new Map((c.data?.documents ?? []).map((d) => [d.id, d]))
  const view = q.data
  const draft = view ? view.sections.some((s) => !s.confirmed) : true
  const canDownload = role === 'coordinator' || role === 'physician'

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl">{t.title}</h2>
          {view && <p className="mt-1 font-medium">{t.asOf(formatDateTime(view.asOf))}</p>}
          <p className="text-xs text-muted">{t.asOfHint}</p>
        </div>
        {canDownload && (
          <div className="max-w-sm text-right">
            <Button
              variant="primary"
              disabled={!view || view.sections.length === 0 || download.isPending}
              onClick={() => view && download.mutate({ fileName: mdtRecordFileName(id, view.asOf, draft) })}
            >
              {download.isPending ? t.downloading : t.download}
            </Button>
            {draft && <p className="mt-1 text-xs text-muted">{t.downloadDraftNote}</p>}
            {download.isError && (
              <p role="alert" className="mt-1 text-xs text-missing">
                {t.downloadError} {problemTitle(download.error)}
              </p>
            )}
          </div>
        )}
      </div>

      {q.isPending && <LoadingBlock lines={6} />}
      {q.isError &&
        (q.error instanceof ApiProblem && q.error.status === 404 ? (
          <EmptyState title={t.notAvailable} hint={t.notAvailableHint} />
        ) : (
          <ErrorState onRetry={() => void q.refetch()} />
        ))}
      {view && view.sections.length === 0 && <EmptyState title={t.notAvailable} hint={t.notAvailableHint} />}

      {view && view.sections.length > 0 && (
        <>
          <Summary sections={view.sections} />
          <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
            <Record view={view} docs={docs} />
            <aside className="space-y-4">
              <Findings sections={view.sections} docs={docs} />
              {view.excluded.length > 0 && (
                <section aria-labelledby="exc-h" className="rounded-lg border border-dashed border-hairline bg-stale-bg/40 p-4">
                  <h3 id="exc-h" className="text-xl">
                    {t.excludedTitle}
                  </h3>
                  <p className="text-xs text-muted">{t.excludedHint}</p>
                  <ul className="mt-2 space-y-1 text-sm">
                    {view.excluded.map((d) => {
                      const doc = docs.get(d.id)
                      return (
                        <li key={d.id}>
                          <StatusPill kind="excluded" /> <span className="font-mono text-xs">{d.id.slice(0, 2)}</span> {doc?.title ?? d.id}{' '}
                          {doc && <span className="text-muted">{formatDate(doc.authored)}</span>}
                          <span className="block text-xs text-muted">{d.reason}</span>
                        </li>
                      )
                    })}
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
