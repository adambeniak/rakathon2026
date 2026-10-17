import { useMutation, useQuery } from '@tanstack/react-query'
import { z } from 'zod'
import { useDemo } from '@/app/DemoContext'
import { caseSummary } from '@/features/cases/schemas'
import { mdtConclusion } from '@/features/gp/api'
import { adaptHandover } from '@/features/handover/adapter'
import { client, unwrap } from '@/lib/api/client'
import { ApiProblem, problemTitle } from '@/lib/api/problem'
import { queryKey, useApiMutation, useApiQuery } from '@/lib/api/query'

// Without `as_of` the API answers with the handover as of the case's `mdt_start`, and `HandoverView.asOf` carries it
// back. The screen never picks a date.
// Provisional `/mdt`, `/mdt/generate` and `/send-feedback` calls are gone: the record is the contract's `mdt-record`.

/**
 * The handover as of the MDT start, stored: `POST /handover` (idempotent per case and as-of, same answer as `GET`)
 * saves the snapshot the readiness gate reads and carries over the physician's earlier decisions on unchanged
 * sections (#122). Under the `['case', id]` key, so a section confirmation refreshes it.
 */
export function useMdtHandover(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'handover', today, 'mdt'],
    queryFn: async () =>
      adaptHandover(unwrap(await client.POST('/api/cases/{case_id}/handover', { params: { path: { case_id: id } } }))),
  })
}

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

/** The signed MDT conclusion; `null` until a KOC physician has signed it (the API answers 404). */
export function useConclusion(caseId: string, enabled: boolean) {
  return useApiQuery({
    key: queryKey('mdt', caseId, 'conclusion'),
    schema: z.union([mdtConclusion, z.null()]),
    enabled,
    fetch: async () => {
      try {
        return unwrap(await client.GET('/api/cases/{case_id}/mdt-conclusion', { params: { path: { case_id: caseId } } }))
      } catch (error) {
        if (error instanceof ApiProblem && error.status === 404) return null
        throw error
      }
    },
  })
}

/** The case events of the MDT screen, all through `POST /api/cases/{id}/transitions`. */
export type LoopEvent =
  | { event: 'mark_ready_mdt'; waivers?: Waiver[] }
  | { event: 'record_mdt_conclusion'; conclusion: string }
  | { event: 'send_feedback' }
  | { event: 'close' }

/** A blocking readiness item the physician waives, with the reason. */
export interface Waiver {
  item: string
  reason: string
}

/**
 * Request body of the transition. The signer of a conclusion or a waiver is the acting user, never a field of the
 * form, and readiness itself is never sent: the server computes it from the persisted handover.
 */
export function loopBody(v: LoopEvent) {
  if (v.event === 'record_mdt_conclusion') return { event: v.event, conclusion: v.conclusion.trim() }
  if (v.event === 'mark_ready_mdt' && v.waivers?.length)
    return { event: v.event, waivers: v.waivers.map((w) => ({ item: w.item, reason: w.reason.trim() })) }
  return { event: v.event }
}

/**
 * The blocking items of a refused `mark_ready_mdt`: the `guard_failed` problem lists the readiness item keys in
 * `blocking_items`. `null` for any other refusal (wrong role or state, readiness check missing, …), and when the
 * list is absent or empty, so the waiver form is never shown without an item to waive.
 */
export function blockingItems(error: unknown): string[] | null {
  if (!(error instanceof ApiProblem) || error.status !== 409 || error.code !== 'guard_failed') return null
  return error.blockingItems?.length ? error.blockingItems : null
}

export function useLoopEvent(caseId: string) {
  return useApiMutation({
    schema: caseSummary,
    mutate: async (v: LoopEvent) =>
      unwrap(await client.POST('/api/cases/{case_id}/transitions', { params: { path: { case_id: caseId } }, body: loopBody(v) })),
  })
}

/** Text for a refused event: the API's Czech title, plus the detail when it sent one. */
export function problemText(error: unknown): string {
  if (!(error instanceof ApiProblem)) return problemTitle(error)
  return error.detail ? `${error.title} (${error.detail})` : error.title
}

export { problemTitle }
