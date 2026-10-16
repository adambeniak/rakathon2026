import { RouterProvider } from 'react-router-dom'
import { render } from '@testing-library/react'
import { Providers, makeQueryClient } from '@/app/providers'
import { createTestRouter } from '@/app/router'
import { setDemo } from '@/lib/demo'
import type { Role } from '@/lib/domain'
import { resetStore } from '@/mocks/fixtures/store'

export function renderRoute(path: string, opts: { role?: Role; today?: string } = {}) {
  resetStore()
  setDemo({ role: opts.role ?? 'coordinator', today: opts.today ?? '2026-10-16' })
  return render(
    <Providers queryClient={makeQueryClient()}>
      <RouterProvider router={createTestRouter(path)} />
    </Providers>,
  )
}
