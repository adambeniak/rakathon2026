import type { components } from '@/lib/api/schema'
import type { Role } from '@/lib/domain'

export interface DemoUser {
  role: Role
  name: string
  title: string
  landing: string
}

/**
 * The person each demo role stands for, named exactly as the backend records them. `X-Demo-Role` maps a role to the
 * first seeded person of that role by PractitionerRole id (`backend/app/security/actor.py` `current_actor`, people in
 * `backend/app/seed/demo_case.py`), and that person is the signer in Provenance and AuditEvent. The contract has no
 * "who am I" endpoint, so the names are mirrored here; `backend/tests/unit/test_demo_actor.py` pins the backend side.
 */
export const DEMO_USERS: Record<Role, DemoUser> = {
  gp: { role: 'gp', name: 'MUDr. Tomáš Řezníček', title: 'Praktický lékař', landing: '/gp' },
  coordinator: {
    role: 'coordinator',
    name: 'Bc. Lucie Dvořáková',
    title: 'Koordinátorka KOC 2',
    landing: '/inbox',
  },
  physician: {
    role: 'physician',
    name: 'doc. MUDr. Pavel Hrubý, Ph.D.',
    title: 'Lékař KOC 2',
    landing: '/inbox',
  },
  reviewer: {
    role: 'reviewer',
    name: 'MUDr. Jitka Benešová',
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
