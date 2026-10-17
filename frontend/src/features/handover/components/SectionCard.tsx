import { Copy, Pencil } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { EvidenceChip } from '@/components/EvidenceChip'
import { StatusPill, pillForHandover } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { handover as t } from '@/i18n/cs/handover'
import type { DocumentInfo } from '@/lib/domain'
import type { SectionReview } from '../api'

/** Label the API gives the item that carries the physician's own value (backend `EDITED_LABEL`). */
const EDITED_LABEL = 'Upraveno lékařem'
import type { RowEvidence, SectionView } from '../types'

/** Document ids cited by the section and by its values, each once, for the copied text. */
function sourceIds(s: SectionView): string[] {
  return [...new Set([...s.evidence.map((e) => e.docId), ...s.rows.flatMap((r) => (r.evidence ?? []).map((e) => e.docId))])]
}

/**
 * Copied text keeps its origin: an unconfirmed section is labelled as an AI draft, a confirmed one says it was
 * assembled with AI and by whom it was confirmed, and the cited documents travel with the values.
 */
function toText(s: SectionView): string {
  const sources = s.edited ? [] : sourceIds(s)
  return [
    s.confirmed ? (s.confirmedBy ? t.copyHeader(s.confirmedBy) : '') : t.draftPrefix,
    `${s.number}. ${s.title}`,
    ...s.rows.map((r) => (r.label ? `${r.label}: ${r.value}` : r.value)),
    ...s.missingItems.map((m) => `${t.missingLabel}: ${m.label} – ${m.reason}${m.owner ? ` (${t.missingOwner(m.owner)})` : ''}`),
    ...(sources.length > 0 ? [t.copySources(sources.join(', '))] : []),
  ]
    .filter((line) => line !== '')
    .join('\n')
}

/** The document list gives the title; without it the dates the API sent with the value are enough for the chip. */
function sourceOf(e: RowEvidence, docs: DocumentInfo[]): DocumentInfo | undefined {
  return docs.find((d) => d.id === e.docId) ?? (e.authored && e.received ? { id: e.docId, title: e.docId, place: '', authored: e.authored, received: e.received } : undefined)
}

export function SectionCard({
  s,
  docs,
  onReview,
  editError,
  busy,
  saving: confirming,
  canConfirm: roleAllowed,
}: {
  s: SectionView
  docs: DocumentInfo[]
  onReview: (r: SectionReview) => Promise<unknown>
  editError: boolean
  busy: boolean
  /** The server is recording a review of this very section. */
  saving: boolean
  canConfirm: boolean
}) {
  const [copied, setCopied] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const field = useRef<HTMLTextAreaElement>(null)
  // The edit button disappears while editing: focus goes to the field, and back to the heading when the form closes.
  useEffect(() => {
    if (editing) field.current?.focus()
  }, [editing])
  function closeEdit() {
    setEditing(false)
    heading.current?.focus()
  }
  // Only plain-text sections can be edited inline; the edit is saved and confirmed in one call.
  const canEdit = roleAllowed && s.editableText !== undefined && !!s.valueHash && !saving
  const missingSection = s.status === 'missing'
  const reviewed = s.confirmed // confirmed or accepted as missing

  function startEdit() {
    setDraft(s.editableText ?? '')
    setEditing(true)
  }

  async function save() {
    setSaving(true)
    try {
      await onReview({ kind: 'edit', section: s, text: draft.trim() })
      closeEdit()
    } catch {
      /* the error flag from the mutation is shown below; keep the form open */
    } finally {
      setSaving(false)
    }
  }

  // "Chybí" only when a field is actually listed as missing; a partial section otherwise shows just "Neúplné".
  const pills = s.acceptedMissing
    ? (['missing'] as const)
    : pillForHandover(s.status, s.confirmed).filter((p) => p !== 'missing' || missingSection || s.missingItems.length > 0)
  const canAct = roleAllowed && !!s.valueHash && !reviewed

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
        <h2 id={`s-${s.key}`} ref={heading} tabIndex={-1} className="text-xl outline-none focus-visible:underline">
          <span className="mr-2 font-mono text-sm text-muted">{s.number}</span>
          {s.title}
        </h2>
        <span className="flex flex-wrap gap-1">
          {pills.map((p) => (
            <StatusPill key={p} kind={p} label={p === 'verified' ? t.confirmedPill : p === 'ai' ? t.draftLabel : undefined} />
          ))}
          {s.edited && (
            <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-hairline px-2.5 py-0.5 text-xs font-medium">
              <Pencil aria-hidden className="h-3.5 w-3.5" />
              {t.editedPill}
            </span>
          )}
        </span>
        {confirming && (
          <span role="status" className="text-xs text-muted">
            {t.saving}
          </span>
        )}
        {s.confirmed && s.confirmedBy && (
          <span className="text-xs text-muted">{s.acceptedMissing ? t.acceptedMissingBy(s.confirmedBy) : t.confirmedBy(s.confirmedBy)}</span>
        )}
      </header>

      <dl className="mt-3 space-y-1">
        {s.rows.map((r, i) => (
          <div key={i} className="flex flex-wrap gap-x-3">
            {r.label ? <dt className="w-44 shrink-0 text-muted">{r.label}</dt> : <dt className="sr-only">{s.title}</dt>}
            <dd className="min-w-0 flex-1">
              {r.value}
              {r.note && <span className="ml-2 text-xs text-muted">{r.note}</span>}
              {r.readOnly && <span className="ml-2 text-xs text-muted">{t.readOnly}</span>}
              {s.edited && r.label === EDITED_LABEL && <span className="ml-2 text-xs text-muted">{t.editedRowNote}</span>}
              {!r.evidence && !r.readOnly && !(s.edited && r.label === EDITED_LABEL) && s.status !== 'missing' && s.key !== '12_examinations' && (
                <span className="ml-2 text-xs text-muted">{t.noRowSource}</span>
              )}
              {r.evidence && (
                <span className="ml-2 inline-flex flex-wrap items-center gap-1 align-middle">
                  {r.evidence.map((e, k) => (
                    <EvidenceChip key={k} row docId={e.docId} quote={e.quote} doc={sourceOf(e, docs)} />
                  ))}
                </span>
              )}
            </dd>
          </div>
        ))}
        {s.missingItems.map((m) => (
          <div key={m.key} className="flex flex-wrap items-center gap-x-3">
            <dt className="w-44 shrink-0 text-muted">{t.missingLabel}</dt>
            <dd>
              <StatusPill kind="missing" /> <span className="ml-1">{m.label}</span>
              <span className="ml-2 text-sm text-muted">
                {m.reason}
                {m.owner && ` · ${t.missingOwner(m.owner)}`}
              </span>
            </dd>
          </div>
        ))}
      </dl>
      {s.note && <p className="mt-2 text-sm text-muted">{s.note}</p>}

      {editing && (
        <div className="mt-3 space-y-2 rounded bg-accent-soft/50 p-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{t.editValueAria(s.title)}</span>
            <textarea
              ref={field}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={3}
              className="rounded border border-hairline bg-card px-2 py-1"
            />
          </label>
          <p className="text-xs text-muted">{t.editHint}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={saving || draft.trim() === '' || draft.trim() === (s.editableText ?? '')} onClick={() => void save()}>
              {t.saveEdit}
            </Button>
            <Button variant="ghost" onClick={closeEdit}>
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

      {s.findings.length > 0 && (
        <ul aria-label={t.findings} className="mt-3 space-y-1 text-sm">
          {s.findings.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded bg-conflict-bg/60 px-2 py-1">
              <StatusPill kind="conflict" />
              <span>{f.message}</span>
              {f.evidence.map((e, k) => (
                <EvidenceChip key={k} row docId={e.docId} quote={e.quote} doc={docs.find((d) => d.id === e.docId)} />
              ))}
            </li>
          ))}
        </ul>
      )}

      <footer className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
        <span className="text-xs text-muted">{s.edited ? t.editedSources : t.evidenceSummary}:</span>
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
          {missingSection && !reviewed ? (
            <Button
              variant="secondary"
              disabled={!canAct || busy}
              onClick={() => void onReview({ kind: 'accept_missing', section: s }).catch(() => undefined)}
              aria-label={t.acceptMissingAria(s.title)}
              title={!roleAllowed ? t.physicianOnly : t.acceptMissingHint}
            >
              {t.acceptMissing}
            </Button>
          ) : (
            <Button
              variant="secondary"
              disabled={!canAct || busy}
              onClick={() => void onReview({ kind: 'confirm', section: s }).catch(() => undefined)}
              aria-label={t.confirmSectionAria(s.title)}
              title={!roleAllowed ? t.physicianOnly : undefined}
            >
              {t.confirmSection}
            </Button>
          )}
        </span>
      </footer>
    </section>
  )
}
