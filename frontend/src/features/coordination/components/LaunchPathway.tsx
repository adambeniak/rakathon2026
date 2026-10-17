import { useState, type FormEvent } from 'react'
import { useDemo } from '@/app/DemoContext'
import { Button } from '@/components/ui/button'
import { coordination as t } from '@/i18n/cs/coordination'
import { problemTitle } from '@/lib/api/problem'
import { DEMO_MDT_START_LOCAL, KOC_PHYSICIANS, useLaunchPathway } from '../api'

/** Launch form of the pathway "Karcinom pankreatu – diagnostika": the indicating physician is required by the API. */
export function LaunchPathway({ caseId, onClose }: { caseId: string; onClose: () => void }) {
  const { today } = useDemo()
  const launch = useLaunchPathway(caseId)
  const [startDate, setStartDate] = useState(today)
  const [indicatedBy, setIndicatedBy] = useState(KOC_PHYSICIANS[0]?.id ?? '')
  const [mdtStartLocal, setMdtStartLocal] = useState(DEMO_MDT_START_LOCAL)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    launch.mutate({ startDate, indicatedBy, mdtStartLocal }, { onSuccess: onClose })
  }
  const field = 'mt-1 block w-full rounded border border-hairline bg-card px-3 py-2 text-sm'

  return (
    <form onSubmit={submit} aria-label={t.launch.title} className="max-w-xl space-y-3 rounded-lg border border-hairline bg-card p-4">
      <h3 className="text-lg">{t.launch.title}</h3>
      <p className="text-sm text-muted">{t.launch.hint}</p>
      <label className="block text-sm font-medium">
        {t.launch.indicatedBy}
        <select required value={indicatedBy} onChange={(e) => setIndicatedBy(e.target.value)} className={field}>
          {KOC_PHYSICIANS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.display}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm font-medium">
        {t.launch.startDate}
        <input required type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className={field} />
      </label>
      <label className="block text-sm font-medium">
        {t.launch.mdtStart}
        <input required type="datetime-local" value={mdtStartLocal} onChange={(e) => setMdtStartLocal(e.target.value)} className={field} />
      </label>
      {launch.isError && (
        <p role="alert" className="text-sm text-missing">
          {t.launch.error} {problemTitle(launch.error)}
        </p>
      )}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={launch.isPending || !indicatedBy || !startDate || !mdtStartLocal}>
          {launch.isPending ? t.launch.submitting : t.launch.submit}
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t.launch.cancel}
        </Button>
      </div>
    </form>
  )
}
