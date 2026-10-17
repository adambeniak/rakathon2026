import { useMutation } from '@tanstack/react-query'
import { client, unwrap } from '@/lib/api/client'
import { problemTitle, type ApiProblem } from '@/lib/api/problem'

// The handover as of the MDT start comes from `features/handover/api.ts` (`useHandover`): without `as_of` the API
// answers with the case's `mdt_start`, and `HandoverView.asOf` carries it back. The screen never picks a date.
// Provisional `/mdt`, `/mdt/generate` and `/send-feedback` calls are gone: the record is the contract's `mdt-record`.

/** Our file name for the downloaded record; `NAVRH` while a section is unconfirmed, like the API's own name. */
export function mdtRecordFileName(caseId: string, asOf: string, draft: boolean): string {
  return `MDT_zapis_${caseId}_${asOf.slice(0, 10)}${draft ? '_NAVRH' : ''}.docx`
}

/** Hands the blob to the browser under `fileName` (the API's Content-Disposition name is not used). */
export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** `GET /api/cases/{id}/mdt-record?format=docx`, saved via blob. Failures surface as `ApiProblem`. */
export function useDownloadMdtRecord(caseId: string) {
  return useMutation<void, ApiProblem, { fileName: string }>({
    mutationFn: async ({ fileName }) => {
      const blob = unwrap(
        await client.GET('/api/cases/{case_id}/mdt-record', {
          params: { path: { case_id: caseId }, query: { format: 'docx' } },
          parseAs: 'blob',
        }),
      )
      saveBlob(blob as unknown as Blob, fileName)
    },
  })
}

export { problemTitle }
