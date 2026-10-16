import { CalendarClock } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useDemo } from '@/app/DemoContext'
import { common } from '@/i18n/cs/common'
import { DEMO_DATES } from '@/lib/demo'
import { formatDate } from '@/lib/date'
import type { Role } from '@/lib/domain'
import { cn } from '@/lib/cn'
import { DEMO_USERS } from '@/mocks/fixtures/people'

const NAV: Record<Role, Array<{ to: string; label: string }>> = {
  gp: [
    { to: '/gp', label: common.nav.gp },
    { to: '/referral/new', label: common.nav.newReferral },
  ],
  coordinator: [{ to: '/inbox', label: common.nav.inbox }],
  physician: [{ to: '/inbox', label: common.nav.inbox }],
  reviewer: [{ to: '/reviewer', label: common.nav.reviewer }],
}

const field = 'min-h-9 rounded border border-hairline bg-card px-2 text-sm'

export function AppShell() {
  const { role, today, setRole, setToday } = useDemo()
  const navigate = useNavigate()
  const user = DEMO_USERS[role]
  const preset = (DEMO_DATES as readonly string[]).includes(today)

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-accent focus:px-3 focus:py-2 focus:text-white"
      >
        {common.skipToContent}
      </a>
      <header className="border-b border-hairline bg-card">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
          <NavLink to="/" className="font-serif text-2xl font-semibold text-accent">
            {common.appName}
          </NavLink>
          <nav aria-label={common.mainNav} className="flex gap-1">
            {NAV[role].map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  cn('rounded px-3 py-1.5 text-sm font-medium hover:bg-accent-soft', isActive && 'bg-accent-soft text-accent')
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex flex-wrap items-end gap-3">
            <label className="flex flex-col text-xs text-muted">
              {common.simulatedDate}
              <select
                className={field}
                value={preset ? today : 'custom'}
                onChange={(e) => e.target.value !== 'custom' && setToday(e.target.value)}
              >
                {DEMO_DATES.map((d) => (
                  <option key={d} value={d}>
                    {formatDate(d)}
                  </option>
                ))}
                {!preset && <option value="custom">{formatDate(today)} ({common.customDate})</option>}
              </select>
            </label>
            <label className="flex flex-col text-xs text-muted">
              {common.role}
              <select
                className={field}
                value={role}
                onChange={(e) => {
                  setRole(e.target.value as Role)
                  navigate('/')
                }}
              >
                {(Object.keys(DEMO_USERS) as Role[]).map((r) => (
                  <option key={r} value={r}>
                    {common.roles[r]}
                  </option>
                ))}
              </select>
            </label>
            <p className="pb-1 text-sm">
              <span className="font-semibold">{user.name}</span>
            </p>
          </div>
        </div>
        <p className="flex items-center justify-center gap-2 bg-accent-soft py-1 text-xs text-accent">
          <CalendarClock aria-hidden className="h-3.5 w-3.5" />
          {common.simulatedDateBanner}: <strong>{formatDate(today)}</strong>
        </p>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto max-w-7xl px-6 py-6 pb-16">
        <Outlet />
      </main>
      <footer className="fixed inset-x-0 bottom-0 z-10 border-t border-hairline bg-card px-6 py-2 text-center text-xs text-muted">
        {common.disclaimer}
      </footer>
    </div>
  )
}
