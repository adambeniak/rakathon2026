import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useDemo } from '@/app/DemoContext'
import { cases as t } from '@/i18n/cs/cases'
import type { CaseDetail } from '@/lib/domain'
import { useClaimCase } from '../api'

/**
 * The one primary action of the case, chosen by state (contracts/case-states.md) and role:
 * Převzít (odeslano) · Vyžádat podklady (triage) · Připravit MDT (kompletni, pripraveno_mdt) · Odeslat závěr (zaver_mdt).
 */
export function CaseAction({ c }: { c: CaseDetail }) {
  const { role } = useDemo()
  const claim = useClaimCase()
  const coordinator = role === 'coordinator'
  const physician = role === 'physician'

  if (c.state === 'odeslano' && coordinator) {
    return (
      <Button variant="primary" disabled={claim.isPending} onClick={() => claim.mutate(c.id)} aria-label={t.actions.claimAria(c.patientName)}>
        {t.actions.claim}
      </Button>
    )
  }
  if (c.state === 'triage' && coordinator) {
    return (
      <Button asChild variant="primary">
        <a href="#triage">{t.actions.requestDocs}</a>
      </Button>
    )
  }
  if ((c.state === 'kompletni' || c.state === 'pripraveno_mdt') && (physician || coordinator)) {
    return (
      <Button asChild variant="primary">
        <Link to={`/cases/${c.id}/mdt`}>{t.actions.prepareMdt}</Link>
      </Button>
    )
  }
  if (c.state === 'zaver_mdt' && coordinator) {
    return (
      <Button asChild variant="primary">
        <Link to={`/cases/${c.id}/mdt`}>{t.actions.sendConclusion}</Link>
      </Button>
    )
  }
  return null
}
