import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { api } from '@/lib/api/http'
import type { TaskItem, TaskPhase } from '@/lib/domain'

// Moved from features/cases/api.ts (unchanged). Not in contracts/openapi.json yet: provisional paths.
// TODO(#34) switch to the generated client / useApiQuery and read the real pathway tasks.
export function useTasks(id: string) {
  const { today } = useDemo()
  return useQuery({
    queryKey: ['case', id, 'tasks', today],
    queryFn: () => api.get<TaskItem[]>(`/api/cases/${id}/tasks`),
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
