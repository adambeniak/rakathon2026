// MOCK copy – replaced by API in F2/F3
import { golden } from './golden'

export const INTERVALS = {
  t1: golden.intervals_days['T1_first_GP_visit_to_KOC_referral'] ?? null,
  t2: golden.intervals_days['T2_KOC_referral_to_MDT'] ?? null,
  t3: golden.intervals_days['T3_MDT_to_oncology_consult'] ?? null,
}
