import { Copy, Pencil } from 'lucide-react'
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
  onEdit,
  editError,
  busy,
  canConfirm: roleAllowed,
}: {
  s: HandoverSection
  docs: DocumentInfo[]
  findings: Finding[]
  onConfirm: (key: string) => void
  onEdit: (key: string, rows: Record<number, string>, reason: string) => Promise<unknown>
  editError: boolean
  busy: boolean
  canConfirm: boolean
}) {
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<number, string>>({})
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const changed = Object.entries(draft).filter(([i, v]) => v !== s.rows[Number(i)]?.value)
  const canEdit = roleAllowed && s.rows.some((r) => !r.readOnly)

  function startEdit() {
    setDraft(Object.fromEntries(s.rows.flatMap((r, i) => (r.readOnly ? [] : [[i, r.value]]))))
    setReason('')
    setEditing(true)
  }

  async function save() {
    setSaving(true)
    try {
      await onEdit(s.key, Object.fromEntries(changed.map(([i, v]) => [Number(i), v])), reason.trim())
      setEditing(false)
    } catch {
      /* the error flag from the mutation is shown below; keep the form open */
    } finally {
      setSaving(false)
    }
  }

  // "Chybí" only when a field is actually listed as missing; a partial section otherwise shows just "Neúplné".
  const edited = s.rows.some((r) => r.note?.startsWith('Upraveno lékařem'))
  const pills = pillForHandover(s.status, s.confirmed).filter((p) => p !== 'missing' || s.status === 'missing' || s.missing.length > 0)
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
          {pills.map((p) =>
            p === 'ai' && edited ? <StatusPill key={p} kind="clarify" label={t.editedPill} /> : <StatusPill key={p} kind={p} />,
          )}
        </span>
        {s.confirmed && s.confirmedBy && <span className="text-xs text-muted">{t.confirmedBy(s.confirmedBy)}</span>}
      </header>

      <dl className="mt-3 space-y-1">
        {s.rows.map((r, i) => (
          <div key={i} className="flex flex-wrap gap-x-3">
            {r.label ? <dt className="w-44 shrink-0 text-muted">{r.label}</dt> : <dt className="sr-only">{s.title}</dt>}
            <dd className="min-w-0 flex-1">
              {editing && !r.readOnly ? (
                <input
                  value={draft[i] ?? ''}
                  onChange={(e) => setDraft({ ...draft, [i]: e.target.value })}
                  aria-label={t.editValueAria(r.label ?? s.title)}
                  className="min-h-9 w-full rounded border border-hairline bg-card px-2"
                />
              ) : (
                <>
                  {r.value}
                  {r.note && <span className="ml-2 text-xs text-muted">{r.note}</span>}
                  {r.readOnly && (
                    <span className="ml-2 inline-flex flex-wrap items-center gap-1 align-middle">
                      <span className="text-xs text-muted">{t.readOnly}</span>
                      {r.evidence?.map((e, k) => (
                        <EvidenceChip key={k} docId={e.docId} quote={e.quote} doc={docs.find((d) => d.id === e.docId)} />
                      ))}
                    </span>
                  )}
                </>
              )}
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

      {editing && (
        <div className="mt-3 space-y-2 rounded bg-accent-soft/50 p-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{t.reasonLabel}</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              required
              className="min-h-9 rounded border border-hairline bg-card px-2"
            />
          </label>
          <p className="text-xs text-muted">{t.editHint}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={saving || changed.length === 0 || reason.trim() === ''} onClick={() => void save()}>
              {t.saveEdit}
            </Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              {t.cancelEdit}
            </Button>
            {editError && (
              <span role="alert" className="text-sm text-missing">
                {t.editError}
              </span>
            )}
          </div>
        </div>
      )}

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
          {canEdit && !editing && (
            <Button variant="ghost" onClick={startEdit} aria-label={t.editAria(s.title)}>
              <Pencil aria-hidden className="h-4 w-4" />
              {t.edit}
            </Button>
          )}
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
