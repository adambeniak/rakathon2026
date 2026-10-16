import { Navigate } from 'react-router-dom'
import { DEMO_USERS } from '@/mocks/fixtures/people'
import { useDemo } from './DemoContext'

export function RoleHome() {
  const { role } = useDemo()
  return <Navigate to={DEMO_USERS[role].landing} replace />
}
