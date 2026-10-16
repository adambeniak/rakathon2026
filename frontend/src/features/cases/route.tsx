import type { RouteObject } from 'react-router-dom'
import { CaseLayout } from './components/CaseLayout'
import { Overview } from './components/Overview'
import { AuditTab, DocumentsTab, MessagesTab, TimelineTab } from './components/Tabs'
import { TasksTab } from '@/features/coordination/components/TasksBoard'

export const routes: RouteObject[] = [
  {
    path: 'cases/:id',
    element: <CaseLayout />,
    children: [
      { index: true, element: <Overview /> },
      { path: 'documents', element: <DocumentsTab /> },
      { path: 'tasks', element: <TasksTab /> },
      { path: 'timeline', element: <TimelineTab /> },
      { path: 'messages', element: <MessagesTab /> },
      { path: 'audit', element: <AuditTab /> },
    ],
  },
]
