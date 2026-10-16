import type { RouteObject } from 'react-router-dom'
import { Referral } from './Referral'

export const routes: RouteObject[] = [{ path: 'referral/new', element: <Referral /> }]
