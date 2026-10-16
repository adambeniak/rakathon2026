import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { api } from '@/lib/api/http'
import { handoverSectionSchema } from '@/lib/domain'
import { z } from 'zod'
import type { HandoverView } from './types'

const viewSchema = z.object({
  asOf: z.string(),
  sections: z.array(handoverSectionSchema),
  excluded: z.array(z.any()),
})

export function useHandover(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'handover', today],
    queryFn: async () => viewSchema.parse(await api.get(`/api/cases/${id}/handover`)) as HandoverView,
  })
}

export function useConfirmSection(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.post(`/api/cases/${id}/handover/sections/${key}/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}

export function useConfirmAll(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post(`/api/cases/${id}/handover/confirm-all`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}
