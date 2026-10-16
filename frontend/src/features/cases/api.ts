import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { api } from '@/lib/api/http'
import { adaptCase, adaptDetail } from './adapter'
import type { AuditEntry, Finding, Message, TaskItem, TimelineEvent } from '@/lib/domain'

function useCaseQuery<T>(id: string, part: string) {
  const { today } = useDemo()
  return useQuery({ queryKey: ['case', id, part, today], queryFn: () => api.get<T>(`/api/cases/${id}/${part}`) })
}

export function useInbox() {
  const { today } = useDemo()
  return useQuery({ queryKey: ['cases', today], queryFn: async () => unwrap(await client.GET('/api/cases')).map(adaptCase) })
}

export function useCase(id: string) {
  const { today } = useDemo()
  return useQuery({ queryKey: ['case', id, 'detail', today], queryFn: async () => adaptDetail(unwrap(await client.GET('/api/cases/{case_id}', { params: { path: { case_id: id } } }))),
  })
}

export const useFindings = (id: string) => useCaseQuery<Finding[]>(id, 'findings')
export function useDocuments(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'documents', today],
    queryFn: async () => adaptDetail(unwrap(await client.GET('/api/cases/{case_id}', { params: { path: { case_id: id } } }))).documents,
  })
}
export const useTasks = (id: string) => useCaseQuery<TaskItem[]>(id, 'tasks')
export const useTimeline = (id: string) => useCaseQuery<TimelineEvent[]>(id, 'timeline')
export const useMessages = (id: string) => useCaseQuery<Message[]>(id, 'messages')
export const useAudit = (id: string) => useCaseQuery<AuditEntry[]>(id, 'audit')

export function useClaimCase() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/cases/${id}/claim`),
    onSuccess: () => qc.invalidateQueries(),
  })
}
