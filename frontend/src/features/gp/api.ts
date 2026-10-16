import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { api } from '@/lib/api/http'
import type { CaseDetail } from '@/lib/domain'

export function useGpCases() {
  const { today } = useDemo()
  return useQuery({ queryKey: ['gp-cases', today], queryFn: () => api.get<CaseDetail[]>('/api/gp/cases') })
}

export function useAcknowledge() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/cases/${id}/acknowledge`),
    onSuccess: () => qc.invalidateQueries(),
  })
}
