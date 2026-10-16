import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import type { Role } from '@/lib/domain'
import { getDemo, setDemo } from '@/lib/demo'

interface DemoValue {
  role: Role
  today: string
  setRole: (r: Role) => void
  setToday: (d: string) => void
}

const Ctx = createContext<DemoValue | null>(null)

export function DemoProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [s, setS] = useState(getDemo())
  const update = useCallback(
    (next: { role: Role; today: string }) => {
      setDemo(next)
      setS(next)
      void qc.invalidateQueries()
    },
    [qc],
  )
  const value = useMemo<DemoValue>(
    () => ({
      ...s,
      setRole: (role) => update({ ...s, role }),
      setToday: (today) => update({ ...s, today }),
    }),
    [s, update],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useDemo(): DemoValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useDemo must be used inside DemoProvider')
  return v
}
