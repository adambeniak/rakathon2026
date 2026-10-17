import { useRef, useState } from 'react'
import { useDemo } from '@/app/DemoContext'
import { useDocumentRequests } from '@/features/cases/api'
import { Button } from '@/components/ui/button'
import { documents as t } from '@/i18n/cs/documents'
import { problemTitle } from '@/lib/api/problem'
import { useUploadDocument } from '../api'

type Result = { name: string; error?: string }

const OPEN_REQUEST = new Set(['requested', 'accepted', 'in_progress'])
const DATE_IN_NAME = /(\d{4}-\d{2}-\d{2})/

/**
 * The open request a report fulfils, by the examination date in its file name (the rule triage uses for "attached").
 * A request is preselected only when exactly one is left for that date; the coordinator can change it.
 */
function preselect(files: File[], open: { id: string; exam_date?: string | null }[]): Record<string, string> {
  const taken = new Set<string>()
  const out: Record<string, string> = {}
  for (const file of files) {
    const date = DATE_IN_NAME.exec(file.name)?.[1]
    const same = open.filter((r) => date && r.exam_date === date && !taken.has(r.id))
    if (same.length === 1) {
      out[file.name] = same[0]!.id
      taken.add(same[0]!.id)
    }
  }
  return out
}

/** Upload of reports by the coordinator. Files go one by one, each with its original name; every outcome is listed. */
export function DocumentUpload({ caseId }: { caseId: string }) {
  const { role } = useDemo()
  if (role !== 'coordinator') return <p className="text-sm text-muted">{t.coordinatorOnly}</p>
  return <UploadForm caseId={caseId} />
}

function UploadForm({ caseId }: { caseId: string }) {
  const upload = useUploadDocument(caseId)
  const requests = useDocumentRequests(caseId)
  const input = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [busy, setBusy] = useState(false)
  const [picked, setPicked] = useState<Record<string, string>>({})

  const open = (requests.data ?? []).filter((r) => OPEN_REQUEST.has(r.status))
  const auto = preselect(files, open)
  const requestOf = (file: File) => picked[file.name] ?? auto[file.name] ?? ''

  async function send() {
    setBusy(true)
    const done: Result[] = []
    for (const file of files) {
      try {
        await upload.mutateAsync({ file, requestId: requestOf(file) || undefined })
        done.push({ name: file.name })
      } catch (error) {
        done.push({ name: file.name, error: problemTitle(error) })
      }
    }
    setResults(done)
    setFiles([])
    setPicked({})
    if (input.current) input.current.value = ''
    setBusy(false)
  }

  return (
    <section aria-label={t.uploadTitle} className="space-y-2 rounded-lg border border-hairline bg-card p-4">
      <h3 className="text-lg">{t.uploadTitle}</h3>
      <p className="text-sm text-muted">{t.uploadHint}</p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">{t.uploadLabel}</span>
          <input
            ref={input}
            type="file"
            multiple
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          />
        </label>
        <Button variant="primary" disabled={busy || files.length === 0} onClick={() => void send()}>
          {busy ? t.uploading : t.uploadButton}
        </Button>
      </div>
      {files.length > 0 && open.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-muted">{t.requestHint}</p>
          {files.map((file) => (
            <label key={file.name} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-mono text-xs">{file.name}</span>
              <select
                aria-label={t.requestFor(file.name)}
                className="min-h-9 max-w-full rounded border border-hairline bg-card px-2 text-sm"
                value={requestOf(file)}
                onChange={(e) => setPicked({ ...picked, [file.name]: e.target.value })}
              >
                <option value="">{t.noRequest}</option>
                {open.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      {results.length > 0 && (
        <ul role="status" className="space-y-1 text-sm">
          {results.map((r) => (
            <li key={r.name} className={r.error ? 'text-missing' : 'text-verified'}>
              {r.error ? t.uploadFailed(r.name, r.error) : t.uploaded(r.name)}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
