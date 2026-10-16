import { createBrowserRouter, createMemoryRouter, Navigate, type RouteObject } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { RoleHome } from './RoleHome'

// Every feature exports `routes: RouteObject[]` from src/features/<feature>/route.tsx.
const modules = import.meta.glob<{ routes: RouteObject[] }>('/src/features/*/route.tsx', { eager: true })
const featureRoutes = Object.values(modules).flatMap((m) => m.routes)

export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <RoleHome /> },
      ...featureRoutes,
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]

export const createRouter = () => createBrowserRouter(routes)
export const createTestRouter = (path: string) => createMemoryRouter(routes, { initialEntries: [path] })
