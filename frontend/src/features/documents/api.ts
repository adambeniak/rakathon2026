import { useQuery } from '@tanstack/react-query'
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
