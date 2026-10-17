import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { coordination } from '@/i18n/cs/coordination'
import { client, unwrap } from '@/lib/api/client'
import { isMocked } from '@/lib/api/mode'
import { problemTitle } from '@/lib/api/problem'
import { isoToPragueLocal, pragueLocalToIso } from '@/lib/date'
import type { Role } from '@/lib/domain'
import { getDemo, setDemo } from '@/lib/demo'

interface DemoValue {
  role: Role
  today: string
  setRole: (r: Role) => void
  setToday: (d: string) => void
}

const Ctx = createContext<DemoValue | null>(null)

/** Time of day the backend clock is pinned to when the demo date switcher picks a day (Prague). */
const CLOCK_TIME = '09:00'

/**
 * Role and simulated date. With the MSW mocks the date is only a query parameter. Against the real backend the
 * backend clock is the single source of truth (`GET/PUT /api/demo/clock`): the switcher moves it, and on load the
 * date is read from it, so deadlines, escalation and countdowns all come from the same time.
 */
export function DemoProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [s, setS] = useState(getDemo())
  const [clockError, setClockError] = useState<string | null>(null)
  const realClock = !isMocked()

  const update = useCallback(
    (patch: Partial<{ role: Role; today: string }>) => {
      const next = { ...getDemo(), ...patch }
      setDemo(next)
      setS(next)
      void qc.invalidateQueries()
    },
    [qc],
  )

  useEffect(() => {
    if (!realClock) return
    client
      .GET('/api/demo/clock')
      .then((r) => {
        const today = isoToPragueLocal(unwrap(r).now).slice(0, 10)
        if (today !== getDemo().today) update({ today })
      })
      .catch((e: unknown) => setClockError(`${coordination.clock.error} ${problemTitle(e)}`))
  }, [realClock, update])

  const value = useMemo<DemoValue>(
    () => ({
      ...s,
      setRole: (role) => update({ role }),
      setToday: (today) => {
        if (!realClock) return update({ today })
        client
          .PUT('/api/demo/clock', { body: { now: pragueLocalToIso(`${today}T${CLOCK_TIME}`) } })
          .then((r) => {
            setClockError(null)
            update({ today: isoToPragueLocal(unwrap(r).now).slice(0, 10) })
          })
          .catch((e: unknown) => setClockError(`${coordination.clock.error} ${problemTitle(e)}`))
      },
    }),
    [s, update, realClock],
  )
  return (
    <Ctx.Provider value={value}>
      {clockError && (
        <p role="alert" className="bg-missing-bg px-4 py-2 text-center text-sm text-missing">
          {clockError}
        </p>
      )}
      {children}
    </Ctx.Provider>
  )
}

export function useDemo(): DemoValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDemo must be used inside DemoProvider')
  return v
}
