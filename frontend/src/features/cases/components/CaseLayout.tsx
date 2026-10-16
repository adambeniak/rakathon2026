import type { ReactNode } from 'react'
import { Link, NavLink, Outlet, useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { cases as t } from '@/i18n/cs/cases'
import { cn } from '@/lib/cn'
import { ApiError } from '@/lib/api/http'
import { useCase } from '../api'
import { CaseHeader } from './CaseHeader'

const TABS = [
  { to: '', label: t.tabs.overview, end: true },
  { to: 'documents', label: t.tabs.documents, end: false },
  { to: 'handover', label: t.tabs.handover, end: false },
  { to: 'tasks', label: t.tabs.tasks, end: false },
  { to: 'timeline', label: t.tabs.timeline, end: false },
  { to: 'messages', label: t.tabs.messages, end: false },
  { to: 'audit', label: t.tabs.audit, end: false },
] as const

/** Case header + tab navigation shared by the case detail, handover and MDT screens. */
export function CaseLayout({ children }: { children?: ReactNode }) {
  const { id = '' } = useParams()
  const q = useCase(id)

  if (q.isPending) return <LoadingBlock lines={5} />
  if (q.isError) {
    if (q.error instanceof ApiError && q.error.status === 404) {
      return (
        <EmptyState
          title={t.notFound}
          hint={t.notFoundHint}
          action={
            <Button asChild variant="secondary">
              <Link to="/">{t.backToInbox}</Link>
            </Button>
          }
        />
      )
    }
    return <ErrorState onRetry={() => void q.refetch()} />
  }

  return (
    <div className="space-y-4">
      <CaseHeader c={q.data} />
      <nav aria-label={t.tabsLabel} className="flex flex-wrap gap-1 border-b border-hairline">
        {TABS.map((tab) => (
          <NavLink
            key={tab.label}
            to={`/cases/${id}${tab.to ? `/${tab.to}` : ''}`}
            end={tab.end}
            className={({ isActive }) =>
              cn(
                '-mb-px border-b-2 px-3 py-2 text-sm font-medium hover:text-accent',
                isActive ? 'border-accent text-accent' : 'border-transparent text-muted',
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div>{children ?? <Outlet />}</div>
    </div>
  )
}
