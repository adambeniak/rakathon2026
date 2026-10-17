import type { components } from '@/lib/api/schema'

type Schemas = components['schemas']

export type Koc = Schemas['KocEntry']
export type ReferralPrefill = Schemas['ReferralPrefill']
export type Evidence = Schemas['Evidence']
export type EvidencedText = Schemas['Evidenced_str_']
export type Priority = 'routine' | 'urgent'
