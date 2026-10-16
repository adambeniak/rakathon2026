import type { Role } from '@/lib/domain'

export interface DemoUser {
  role: Role
  name: string
  title: string
  landing: string
}

export const DEMO_USERS: Record<Role, DemoUser> = {
  gp: { role: 'gp', name: 'MUDr. Řezníček', title: 'Praktický lékař', landing: '/gp' },
  coordinator: {
    role: 'coordinator',
    name: 'Bc. Dvořáková',
    title: 'Koordinátorka KOC 2',
    landing: '/inbox',
  },
  physician: {
    role: 'physician',
    name: 'MUDr. Havelka',
    title: 'Lékař KOC 2',
    landing: '/inbox',
  },
  reviewer: {
    role: 'reviewer',
    name: 'MUDr. Soukupová',
    title: 'Revizní lékař ZP 211',
    landing: '/reviewer',
  },
}

export const KOC_DIRECTORY = [
  { id: 'koc1', name: 'KOC 1 – Nemocnice Severní' },
  { id: 'koc2', name: 'KOC 2 – Nemocnice Lipová' },
] as const
