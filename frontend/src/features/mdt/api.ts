import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api/http'
import type { MdtView } from './types'

export function useMdt(id: string, asOf: string) {
  return useQuery({
    queryKey: ['case', id, 'mdt', asOf],
    queryFn: () => api.get<MdtView>(`/api/cases/${id}/mdt?as_of=${encodeURIComponent(asOf)}`),
  })
}

export function useSendFeedback(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post(`/api/cases/${id}/send-feedback`),
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useGenerateMdt(id: string, asOf: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post(`/api/cases/${id}/mdt/generate?as_of=${encodeURIComponent(asOf)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}
