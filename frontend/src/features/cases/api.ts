import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { api } from '@/lib/api/http'
import type { AuditEntry, CaseDetail, CaseSummary, DocumentInfo, Finding, Message, TaskItem, TimelineEvent } from '@/lib/domain'

function useCaseQuery<T>(id: string, part: string) {
  const { today } = useDemo()
  return useQuery({ queryKey: ['case', id, part, today], queryFn: () => api.get<T>(`/api/cases/${id}/${part}`) })
}

export function useInbox() {
  const { today } = useDemo()
  return useQuery({ queryKey: ['cases', today], queryFn: () => api.get<CaseSummary[]>('/api/cases') })
}

export function useCase(id: string) {
  const { today } = useDemo()
  return useQuery({ queryKey: ['case', id, 'detail', today], queryFn: () => api.get<CaseDetail>(`/api/cases/${id}`) })
}

export const useFindings = (id: string) => useCaseQuery<Finding[]>(id, 'findings')
export const useDocuments = (id: string) => useCaseQuery<DocumentInfo[]>(id, 'documents')
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
