import { useQuery } from '@tanstack/react-query'
import { useDemo } from '@/app/DemoContext'
import { api } from '@/lib/api/http'
import type { CaseDetail } from '@/lib/domain'

export function useReviewerCases() {
  const { today } = useDemo()
  return useQuery({ queryKey: ['reviewer-cases', today], queryFn: () => api.get<CaseDetail[]>('/api/reviewer/cases') })
}
