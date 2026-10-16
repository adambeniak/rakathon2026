import { UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { EvidenceChip } from '@/components/EvidenceChip'
import { StatusPill } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { referral as t } from '@/i18n/cs/referral'
import { formatDate } from '@/lib/date'
import { cn } from '@/lib/cn'
import type { ReferralEvidence } from './types'
import { useKocDirectory, useParseReferral, useSubmitReferral } from './api'

function Chip({ e }: { e: ReferralEvidence }) {
  return <EvidenceChip docId={e.docId} quote={e.quote} doc={e.doc} />
}

export function Referral() {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [koc, setKoc] = useState('')
  const [consent, setConsent] = useState(false)
  const [note, setNote] = useState('')
  const kocs = useKocDirectory()
  const parse = useParseReferral()
  const submit = useSubmitReferral()
  const parsed = parse.data

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    const f = e.dataTransfer.files[0]
    if (f) parse.mutate(f.name)
  }

  if (submit.isSuccess) {
    return (
      <section className="mx-auto max-w-xl space-y-3 rounded-lg border border-hairline bg-card p-8 text-center" role="status">
        <h1 className="text-3xl">{t.sentTitle}</h1>
        <div className="flex items-center justify-center gap-2">
          <span className="text-sm text-muted">{t.stateLabel}:</span>
          <CaseStateBadge state={submit.data.state} />
        </div>
        <p className="text-muted">{t.sentHint}</p>
        <div className="text-left">
          <h2 className="text-lg">{t.nextTitle}</h2>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">
            {t.nextSteps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
        <Button asChild variant="primary">
          <Link to="/gp">{t.sentLink}</Link>
        </Button>
      </section>
    )
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <h1 className="text-3xl">{t.title}</h1>

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          'flex flex-col items-center gap-2 rounded-lg border-2 border-dashed bg-card px-6 py-8 text-center',
          over ? 'border-accent bg-accent-soft' : 'border-hairline',
        )}
      >
        <UploadCloud aria-hidden className="h-7 w-7 text-accent" />
        <p className="font-serif text-xl">{t.dropTitle}</p>
        <p className="text-sm text-muted">{t.dropHint}</p>
        <input
          ref={input}
          type="file"
          accept=".pdf,.docx,.txt"
          aria-label={t.fileInputLabel}
          className="sr-only"
          onChange={(e) => e.target.files?.[0] && parse.mutate(e.target.files[0].name)}
        />
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => input.current?.click()}>
            {t.chooseFile}
          </Button>
          <Button variant="ghost" onClick={() => parse.mutate('07_PL_zadost_KOC2_2026-10-02.pdf')}>
            {t.useSample}
          </Button>
        </div>
        {parse.isPending && <p role="status">{t.parsing}</p>}
      </div>

      {parsed && (
        <section aria-labelledby="sum-h" className="space-y-3 rounded-lg border border-hairline bg-card p-5">
          <div className="flex items-center gap-2">
            <h2 id="sum-h" className="text-xl">
              {t.summaryTitle}
            </h2>
            <StatusPill kind="ai" />
          </div>
          <p className="text-sm text-muted">{t.summaryHint}</p>
          <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-[10rem_1fr]">
            <dt className="text-muted">{t.fields.patient}</dt>
            <dd className="flex flex-wrap items-center gap-2 font-medium">
              {parsed.patientName}
              <Chip e={parsed.evidence.patientName} />
            </dd>
            <dt className="text-muted">{t.fields.birthDate}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              {formatDate(parsed.birthDate)}
              <Chip e={parsed.evidence.birthDate} />
            </dd>
            <dt className="text-muted">{t.fields.birthNumber}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              {parsed.birthNumber}
              <Chip e={parsed.evidence.birthNumber} />
            </dd>
            <dt className="text-muted">{t.fields.insurer}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              {parsed.insurer}
              <Chip e={parsed.evidence.insurer} />
            </dd>
            <dt className="text-muted">{t.fields.diagnosis}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              {parsed.diagnosis}
              <Chip e={parsed.evidence.diagnosis} />
            </dd>
            <dt className="text-muted">{t.fields.urgency}</dt>
            <dd className="flex flex-wrap items-center gap-2">
              {parsed.urgent ? t.urgent : '—'}
              <Chip e={parsed.evidence.urgent} />
            </dd>
          </dl>
        </section>
      )}

      <section className="space-y-4 rounded-lg border border-hairline bg-card p-5">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{t.kocLabel}</span>
          <select
            value={koc}
            onChange={(e) => setKoc(e.target.value)}
            className="min-h-10 max-w-md rounded border border-hairline bg-card px-2"
          >
            <option value="">{t.kocPlaceholder}</option>
            {kocs.data?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-start gap-2">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-1 h-4 w-4 accent-[var(--accent)]" />
          <span>{t.consent}</span>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{t.noteLabel}</span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={500}
            aria-describedby="note-hint"
            className="max-w-xl rounded border border-hairline bg-card p-2"
          />
          <span id="note-hint" className="text-xs text-muted">
            {t.noteHint}
          </span>
        </label>
        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            disabled={!parsed || !koc || !consent || submit.isPending}
            onClick={() =>
              parsed && submit.mutate({ kocId: koc, consent, filename: parsed.filename, note: note.trim() || undefined })
            }
          >
            {submit.isPending ? t.submitting : t.submit}
          </Button>
          {!parsed && <span className="text-sm text-muted">{t.needFile}</span>}
          {submit.isError && (
            <span role="alert" className="text-sm text-missing">
              {t.error}
            </span>
          )}
        </div>
      </section>
    </div>
  )
}
