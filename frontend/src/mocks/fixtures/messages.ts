// MOCK copy – replaced by API in F2/F3
import type { AuditEntry, Message } from '@/lib/domain'
import { DEMO_USERS } from './people'

export const MESSAGES: Message[] = [
  { id: 'm1', at: '2026-10-02T10:05:00+02:00', from: DEMO_USERS.gp.name, to: 'Koordinace KOC 2', subject: 'Žádost o převzetí pacientky', body: 'Žádost o převzetí do péče KOC 2 odeslána včetně souhlasu pacientky.' },
  { id: 'm2', at: '2026-10-02T11:30:00+02:00', from: DEMO_USERS.coordinator.name, to: DEMO_USERS.gp.name, subject: 'Žádost převzata', body: 'Případ převzat do triage. Žádáme o doložení výsledků 01–06.' },
  { id: 'm3', at: '2026-10-16T09:00:00+02:00', from: 'Systém', to: DEMO_USERS.coordinator.name, subject: 'Eskalace termínu', body: 'Termín výsledku histologie byl překročen.' },
]

export const AUDIT: AuditEntry[] = [
  { at: '2026-10-02T10:05:00+02:00', who: DEMO_USERS.gp.name, action: 'Odeslání žádosti o převzetí (souhlas pacientky zaznamenán)' },
  { at: '2026-10-02T11:28:00+02:00', who: DEMO_USERS.coordinator.name, action: 'Převzetí případu do triage' },
  { at: '2026-10-08T15:10:00+02:00', who: DEMO_USERS.coordinator.name, action: 'Nahrány dokumenty 01–06 a 08' },
  { at: '2026-10-12T14:20:00+02:00', who: 'Systém', action: 'Přijat protokol výkonu 09; nalezen nesoulad dat' },
  { at: '2026-10-19T12:10:00+02:00', who: 'Systém', action: 'Přijata histologie 11; nalezen nesoulad dat' },
  { at: '2026-10-20T09:15:00+02:00', who: DEMO_USERS.physician.name, action: 'Zobrazen handover' },
]
