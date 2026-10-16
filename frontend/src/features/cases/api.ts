import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { client, unwrap } from '@/lib/api/client'
import { api } from '@/lib/api/http'
import { adaptCase, adaptDetail } from './adapter'
import type { AuditEntry, DocumentRequest, Finding, Message, TaskItem, TaskPhase, TimelineEvent } from '@/lib/domain'

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

// --- Not in contracts/openapi.json yet (F2-x): provisional paths, replace with the generated client when they land.

export const useDocumentRequests = (id: string) => useCaseQuery<DocumentRequest[]>(id, 'document-requests')

export function useRequestDocuments(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => api.post(`/api/cases/${id}/document-requests`, { ids }),
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useStartTaskSet(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post(`/api/cases/${id}/task-sets`, { code: 'pankreas-diagnostika' }),
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useAdvanceTask(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { taskId: string; phase: TaskPhase }) =>
      api.post(`/api/cases/${id}/tasks/${v.taskId}/phase`, { phase: v.phase }),
    onSuccess: () => qc.invalidateQueries(),
  })
}
