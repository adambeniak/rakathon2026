import type { components } from '@/lib/api/schema'
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

export const KOC_DIRECTORY: Array<components['schemas']['KocEntry']> = [
  {
    id: 'koc1-nemocnice-severni',
    name: 'KOC 1 – Komplexní onkologické centrum Nemocnice Severní',
    city: 'Praha 8',
    coordinator: { id: 'koordinator@koc1-nemocnice-severni', display: 'Koordinátor KOC 1' },
  },
  {
    id: 'koc2-nemocnice-lipova',
    name: 'KOC 2 – Komplexní onkologické centrum Nemocnice Lipová',
    city: 'Praha 4',
    coordinator: { id: 'dvorakova-lucie@koc2-nemocnice-lipova', display: 'Koordinátor KOC 2' },
  },
]
