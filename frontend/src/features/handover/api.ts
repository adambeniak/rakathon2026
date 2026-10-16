import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { api } from '@/lib/api/http'
import { handoverSectionSchema } from '@/lib/domain'
import { z } from 'zod'
import type { HandoverView } from './types'

const viewSchema = z.object({
  asOf: z.string(),
  sections: z.array(handoverSectionSchema),
  excluded_documents: z.array(z.any()),
})

export function useHandover(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'handover', today],
    queryFn: async () => {
      const v = viewSchema.parse(await api.get(`/api/cases/${id}/handover`))
      return { asOf: v.asOf, sections: v.sections, excluded: v.excluded_documents } as HandoverView
    },
  })
}

/** Confirmation is the only optimistic write: the pill flips at once and rolls back if the server refuses. */
export function useConfirmSection(id: string) {
  const qc = useQueryClient()
  const { today } = useDemo()
  const key = ['case', id, 'handover', today]
  return useMutation({
    mutationFn: (sectionKey: string) => api.post(`/api/cases/${id}/handover/sections/${sectionKey}/confirm`),
    onMutate: async (sectionKey: string) => {
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<HandoverView>(key)
      if (previous) {
        qc.setQueryData<HandoverView>(key, {
          ...previous,
          sections: previous.sections.map((s) => (s.key === sectionKey ? { ...s, confirmed: true } : s)),
        })
      }
      return { previous }
    },
    onError: (_e, _k, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}

export function useConfirmAll(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post(`/api/cases/${id}/handover/confirm-all`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}

/** Inline edit of a section: new row values plus the reason the clinician gives (recorded as Provenance). */
export function useEditSection(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { sectionKey: string; rows: Record<number, string>; reason: string }) =>
      api.post(`/api/cases/${id}/handover/sections/${v.sectionKey}/edit`, { rows: v.rows, reason: v.reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['case', id] }),
  })
}
