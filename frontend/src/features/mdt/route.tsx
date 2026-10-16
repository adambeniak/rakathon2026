import type { RouteObject } from 'react-router-dom'
import { CaseLayout } from '@/features/cases/components/CaseLayout'
import { Mdt } from './Mdt'

export const routes: RouteObject[] = [
  {
    path: 'cases/:id/mdt',
    element: (
      <CaseLayout>
        <Mdt />
      </CaseLayout>
    ),
  },
]
