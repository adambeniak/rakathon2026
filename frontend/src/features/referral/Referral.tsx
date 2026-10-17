import { UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { CaseStateBadge } from '@/components/CaseStateBadge'
import { EvidenceChip } from '@/components/EvidenceChip'
import { StatusPill } from '@/components/StatusPill'
import { Button } from '@/components/ui/button'
import { referral as t } from '@/i18n/cs/referral'
import { isMocked } from '@/lib/api/mode'
import { problemTitle } from '@/lib/api/problem'
import { cn } from '@/lib/cn'
import { formatDate } from '@/lib/date'
import { useKocDirectory, usePrefillReferral, useSubmitReferral } from './api'
import { buildSubmission, defaultPriority, missingFields } from './submission'
import type { Evidence, Priority } from './types'

const SAMPLE_LETTER = '07_PL_zadost_KOC2_2026-10-02.docx'

function Chips({ evidence }: { evidence?: Evidence[] }) {
  return (
    <>
      {evidence?.map((e) => (
        <EvidenceChip key={`${e.doc_id}:${e.quote}`} docId={e.doc_id} quote={e.quote} />
      ))}
    </>
  )
}

/** One read value with its source; a value the letter does not state shows Chybí, never a guess. */
function Row({ label, value, evidence, children }: { label: string; value?: ReactNode; evidence?: Evidence[]; children?: ReactNode }) {
  const empty = value === undefined || value === null || value === ''
  return (
    <>
      <dt className="text-muted">{label}</dt>
      <dd className="flex flex-wrap items-center gap-2">
        {empty ? <StatusPill kind="missing" /> : value}
        {!empty && <Chips evidence={evidence} />}
        {children}
      </dd>
    </>
  )
}

const unique = (...lists: Array<Evidence[] | undefined>) => {
  const seen = new Map<string, Evidence>()
  for (const e of lists.flatMap((l) => l ?? [])) seen.set(`${e.doc_id}:${e.quote}`, e)
  return [...seen.values()]
}

export function Referral() {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [koc, setKoc] = useState('')
  const [consent, setConsent] = useState(false)
  const [note, setNote] = useState('')
  const [priorityChoice, setPriorityChoice] = useState<Priority | null>(null)
  const kocs = useKocDirectory()
  const parse = usePrefillReferral()
  const submit = useSubmitReferral()
  const parsed = parse.data

  function pick(f: File | undefined) {
    if (!f) return
    setFile(f)
    setPriorityChoice(null)
    parse.mutate(f)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setOver(false)
    pick(e.dataTransfer.files[0])
  }

  const missing = parsed ? missingFields(parsed) : []
  const priority = priorityChoice ?? (parsed ? defaultPriority(parsed) : 'routine')
  const submission = parsed && koc ? buildSubmission(parsed, { kocId: koc, consent, priority, note }) : null

  const todo: string[] = []
  if (!koc) todo.push(t.todo.koc)
  if (!consent) todo.push(t.todo.consent)

  if (submit.isSuccess) {
    const created = submit.data
    return (
      <section className="mx-auto max-w-xl space-y-3 rounded-lg border border-hairline bg-card p-8 text-center" role="status">
        <h1 className="text-3xl">{t.sentTitle}</h1>
        <div className="flex items-center justify-center gap-2">
          <span className="text-sm text-muted">{t.stateLabel}:</span>
          <CaseStateBadge state={created.case.state} />
        </div>
        {created.case.baton_holder && (
          <p className="text-sm">
            <span className="text-muted">{t.batonLabel}:</span> <span className="font-medium">{created.case.baton_holder.display}</span>
          </p>
        )}
        <p className="text-muted">{t.sentHint}</p>
        {created.warnings.map((w) => (
          <p key={w} className="text-sm text-muted">
            {t.warnings[w as keyof typeof t.warnings] ?? t.warningGeneric(w)}
          </p>
        ))}
        <div className="text-left">
          <h2 className="text-lg">{t.nextTitle}</h2>
          <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">
            {t.nextSteps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
        <div className="flex items-center justify-center gap-4">
          <Button asChild variant="primary">
            <Link to="/gp">{t.sentLink}</Link>
          </Button>
          <Link to={`/cases/${created.case.id}`} className="text-sm text-accent underline">
            {t.openCase}
          </Link>
        </div>
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
          accept=".pdf,.docx"
          aria-label={t.fileInputLabel}
          className="sr-only"
          onChange={(e) => pick(e.target.files?.[0])}
        />
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="secondary" onClick={() => input.current?.click()}>
            {t.chooseFile}
          </Button>
          {/* The sample has no file behind it on the real backend, which reads the uploaded letter itself. */}
          {isMocked() && (
            <Button variant="ghost" onClick={() => pick(new File(['Žádost PL o převzetí do KOC'], SAMPLE_LETTER))}>
              {t.useSample}
            </Button>
          )}
        </div>
        {parse.isPending && <p role="status">{t.parsing}</p>}
        {parse.isError && (
          <p role="alert" className="text-sm text-missing">
            {t.prefillError} {problemTitle(parse.error)}
          </p>
        )}
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
            <Row
              label={t.fields.patient}
              value={[parsed.given.value, parsed.family.value].filter(Boolean).join(' ')}
              evidence={unique(parsed.given.evidence, parsed.family.evidence)}
            />
            <Row label={t.fields.birthDate} value={parsed.birth_date.value && formatDate(parsed.birth_date.value)} evidence={parsed.birth_date.evidence} />
            <Row label={t.fields.birthNumber} value={parsed.birth_number.value} evidence={parsed.birth_number.evidence} />
            <Row
              label={t.fields.insurer}
              value={parsed.insurer_code.value && [parsed.insurer_code.value, parsed.insurer_name].filter(Boolean).join(' – ')}
              evidence={parsed.insurer_code.evidence}
            />
            <Row
              label={t.fields.diagnosis}
              value={
                parsed.suspected_diagnosis.value &&
                [parsed.suspected_diagnosis.value.code, parsed.suspected_diagnosis.value.text].filter(Boolean).join(' – ')
              }
              evidence={parsed.suspected_diagnosis.evidence}
            />
            <Row label={t.fields.phone} value={parsed.patient_phone.value} evidence={parsed.patient_phone.evidence} />
            <Row
              label={t.fields.contact}
              value={
                parsed.contact_person.value &&
                `${parsed.contact_person.value.name} (${parsed.contact_person.value.relation})${
                  parsed.contact_person.value.phone ? `, ${parsed.contact_person.value.phone}` : ''
                }`
              }
              evidence={parsed.contact_person.evidence}
            />
            <dt className="text-muted">{t.fields.consentStatements}</dt>
            <dd className="space-y-1">
              {parsed.consent_statements.length === 0 && <StatusPill kind="missing" />}
              {parsed.consent_statements.map((s) => (
                <span key={s.value} className="flex flex-wrap items-center gap-2">
                  {s.value}
                  <Chips evidence={s.evidence} />
                </span>
              ))}
            </dd>
            <Row label={t.fields.urgency} value={parsed.urgency_statement.value} evidence={parsed.urgency_statement.evidence} />
          </dl>
          {missing.length > 0 && (
            <p role="alert" className="text-sm text-missing">
              {t.missingBlock(missing.map((f) => t.requiredFields[f]))}
            </p>
          )}
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
          {kocs.isError && (
            <span role="alert" className="text-missing">
              {t.kocError} {problemTitle(kocs.error)}
            </span>
          )}
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{t.priorityLabel}</span>
          <select
            value={priority}
            onChange={(e) => setPriorityChoice(e.target.value as Priority)}
            className="min-h-10 max-w-xs rounded border border-hairline bg-card px-2"
          >
            <option value="routine">{t.priority.routine}</option>
            <option value="urgent">{t.priority.urgent}</option>
          </select>
          <span className="text-xs text-muted">{t.priorityHint}</span>
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
            disabled={!file || !submission || !consent || submit.isPending}
            onClick={() => file && submission && submit.mutate({ letter: file, submission })}
          >
            {submit.isPending ? t.submitting : t.submit}
          </Button>
          {!parsed && <span className="text-sm text-muted">{t.needFile}</span>}
          {parsed && todo.length > 0 && <span className="text-sm text-muted">{t.stillNeeded(todo)}</span>}
          {submit.isError && (
            <span role="alert" className="text-sm text-missing">
              {t.error} {problemTitle(submit.error)}
            </span>
          )}
        </div>
      </section>
    </div>
  )
}
