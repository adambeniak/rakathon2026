import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { adaptDetail } from '@/features/cases/adapter'
import { useHandover } from '@/features/handover/api'
import { client, unwrap } from '@/lib/api/client'

/** Documents of the case; the "po MDT" flag comes from the handover's `excluded_documents`, not from dates. */
export function useDocuments(id: string) {
  const { today } = useDemo()
  const handover = useHandover(id)
  const q = useQuery({
    queryKey: ['case', id, 'documents', today],
    queryFn: async () => adaptDetail(unwrap(await client.GET('/api/cases/{case_id}', { params: { path: { case_id: id } } }))).documents,
  })
  const excluded = handover.isSuccess ? new Set(handover.data.excluded.map((d) => d.id)) : undefined
  return {
    ...q,
    isPending: q.isPending || handover.isPending,
    isError: q.isError || handover.isError,
    refetch: async () => {
      await Promise.all([q.refetch(), handover.refetch()])
    },
    data: q.data?.map((d) => ({ ...d, afterAsOf: excluded?.has(d.id) })),
  }
}

/** The multipart body of `POST /api/cases/{case_id}/documents`; the file keeps its original name (it is the LLM cache key). */
export function uploadForm(file: File, opts: { authoredAt?: string; requestId?: string } = {}): FormData {
  const form = new FormData()
  form.append('file', file, file.name)
  if (opts.authoredAt) form.append('authored_at', opts.authoredAt)
  if (opts.requestId) form.append('request_id', opts.requestId)
  return form
}

/** Uploads one report; the handover, the case and the document list are refetched afterwards. */
export function useUploadDocument(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (v: { file: File; authoredAt?: string; requestId?: string }) =>
      unwrap(
        await client.POST('/api/cases/{case_id}/documents', {
          params: { path: { case_id: id } },
          // The generated type of the file part is a string; the real body is built by `bodySerializer`.
          body: { file: v.file.name },
          bodySerializer: () => uploadForm(v.file, v),
        }),
      ),
    // A report that closes a request changes the request list and the case state (queue); `cases` is the triage feature.
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ['case', id] }), qc.invalidateQueries({ queryKey: ['cases'] })]),
  })
}
