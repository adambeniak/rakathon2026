import type { RouteObject } from 'react-router-dom'
import { CaseLayout } from '@/features/cases/components/CaseLayout'
import { Handover } from './Handover'

export const routes: RouteObject[] = [
  {
    path: 'cases/:id/handover',
    element: (
      <CaseLayout>
        <Handover />
      </CaseLayout>
    ),
  },
]
