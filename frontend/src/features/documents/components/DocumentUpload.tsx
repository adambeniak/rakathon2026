import { useRef, useState } from 'react'
import { useDemo } from '@/app/DemoContext'
import { Button } from '@/components/ui/button'
import { documents as t } from '@/i18n/cs/documents'
import { problemTitle } from '@/lib/api/problem'
import { useUploadDocument } from '../api'

type Result = { name: string; error?: string }

/** Upload of reports by the coordinator. Files go one by one, each with its original name; every outcome is listed. */
export function DocumentUpload({ caseId }: { caseId: string }) {
  const { role } = useDemo()
  const upload = useUploadDocument(caseId)
  const input = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [busy, setBusy] = useState(false)

  if (role !== 'coordinator') return <p className="text-sm text-muted">{t.coordinatorOnly}</p>

  async function send() {
    setBusy(true)
    const done: Result[] = []
    for (const file of files) {
      try {
        await upload.mutateAsync({ file })
        done.push({ name: file.name })
      } catch (error) {
        done.push({ name: file.name, error: problemTitle(error) })
      }
    }
    setResults(done)
    setFiles([])
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
