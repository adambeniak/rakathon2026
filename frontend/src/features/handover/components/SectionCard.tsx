import { Copy } from 'lucide-react'
import { useState } from 'react'
import { EvidenceChip } from '@/components/EvidenceChip'
import { StatusPill, pillForHandover } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { handover as t } from '@/i18n/cs/handover'
import type { DocumentInfo, Finding, HandoverSection } from '@/lib/domain'

function toText(s: HandoverSection): string {
  return [`${s.number}. ${s.title}`, ...s.rows.map((r) => (r.label ? `${r.label}: ${r.value}` : r.value)), ...s.missing.map((m) => `${t.missingLabel}: ${m}`)].join('\n')
}

export function SectionCard({
  s,
  docs,
  findings,
  onConfirm,
  busy,
  canConfirm: roleAllowed,
}: {
  s: HandoverSection
  docs: DocumentInfo[]
  findings: Finding[]
  onConfirm: (key: string) => void
  busy: boolean
  canConfirm: boolean
}) {
  const [copied, setCopied] = useState(false)
  const pills = pillForHandover(s.status, s.confirmed)
  const canConfirm = roleAllowed && s.status !== 'missing' && !s.confirmed

  async function copy() {
    try {
      await navigator.clipboard.writeText(toText(s))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section aria-labelledby={`s-${s.key}`} className="rounded-lg border border-hairline bg-card p-4">
      <header className="flex flex-wrap items-center gap-2">
        <h2 id={`s-${s.key}`} className="text-xl">
          <span className="mr-2 font-mono text-sm text-muted">{s.number}</span>
          {s.title}
        </h2>
        <span className="flex flex-wrap gap-1">
          {pills.map((p) => (
            <StatusPill key={p} kind={p} />
          ))}
        </span>
        {s.confirmed && s.confirmedBy && <span className="text-xs text-muted">{t.confirmedBy(s.confirmedBy)}</span>}
      </header>

      <dl className="mt-3 space-y-1">
        {s.rows.map((r, i) => (
          <div key={i} className="flex flex-wrap gap-x-3">
            {r.label ? <dt className="w-44 shrink-0 text-muted">{r.label}</dt> : <dt className="sr-only">{s.title}</dt>}
            <dd className="min-w-0 flex-1">
              {r.value}
              {r.note && <span className="ml-2 text-xs text-muted">{r.note}</span>}
            </dd>
          </div>
        ))}
        {s.missing.map((m) => (
          <div key={m} className="flex flex-wrap items-center gap-x-3">
            <dt className="w-44 shrink-0 text-muted">{t.missingLabel}</dt>
            <dd>
              <StatusPill kind="missing" /> <span className="ml-1">{m}</span>
            </dd>
          </div>
        ))}
      </dl>

      {findings.length > 0 && (
        <ul aria-label={t.findings} className="mt-3 space-y-1 text-sm">
          {findings.map((f) => (
            <li key={f.id} className="rounded bg-conflict-bg/60 px-2 py-1">
              {f.detail}
            </li>
          ))}
        </ul>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
        <span className="text-xs text-muted">{t.evidence}:</span>
        {s.evidence.length === 0 && <span className="text-xs text-muted">{t.noEvidence}</span>}
        {s.evidence.map((e, i) => (
          <EvidenceChip key={`${e.docId}-${i}`} docId={e.docId} quote={e.quote} doc={docs.find((d) => d.id === e.docId)} />
        ))}
        <span className="ml-auto flex items-center gap-2">
          <span role="status" className="text-xs text-verified">
            {copied ? t.copied : ''}
          </span>
          <Button variant="ghost" onClick={() => void copy()} aria-label={t.copyAria(s.title)}>
            <Copy aria-hidden className="h-4 w-4" />
            {t.copy}
          </Button>
          <Button
            variant="secondary"
            disabled={!canConfirm || busy}
            onClick={() => onConfirm(s.key)}
            aria-label={t.confirmSectionAria(s.title)}
            title={!roleAllowed ? t.physicianOnly : s.status === 'missing' ? t.cannotConfirm : undefined}
          >
            {t.confirmSection}
          </Button>
        </span>
      </footer>
    </section>
  )
}
