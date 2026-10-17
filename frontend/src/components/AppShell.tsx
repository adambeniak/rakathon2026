import { CalendarClock } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useDemo } from '@/app/DemoContext'
import { common } from '@/i18n/cs/common'
import { shell } from '@/i18n/cs/shell'
import { DEMO_DATES } from '@/lib/demo'
import { formatDate } from '@/lib/date'
import type { Role } from '@/lib/domain'
import { cn } from '@/lib/cn'
import { DEMO_USERS } from '@/mocks/fixtures/people'
import { TextSizeToggle } from './TextSizeToggle'

const NAV: Record<Role, Array<{ to: string; label: string }>> = {
  gp: [
    { to: '/gp', label: common.nav.gp },
    { to: '/referral/new', label: common.nav.newReferral },
  ],
  coordinator: [{ to: '/inbox', label: common.nav.inbox }],
  physician: [{ to: '/inbox', label: common.nav.inbox }],
  reviewer: [
    { to: '/reviewer', label: common.nav.reviewer },
    { to: '/insurer', label: shell.nav.insurer },
  ],
}

/** Page gutters: 20px on phones, 48px on desktop; content max 1240px. */
const page = 'mx-auto w-full max-w-page px-5 lg:px-12'
const field =
  'min-h-10 rounded-md border-[1.5px] border-line-strong bg-card px-3 text-sm font-medium text-ink hover:bg-sunken'

export function AppShell() {
  const { role, today, setRole, setToday } = useDemo()
  const navigate = useNavigate()
  const user = DEMO_USERS[role]
  const preset = (DEMO_DATES as readonly string[]).includes(today)
  return (
    <div className="min-h-screen overflow-x-clip">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-accent focus:px-4 focus:py-3 focus:font-semibold focus:text-accent-on"
      >
        {common.skipToContent}
      </a>
      <header className="border-b border-hairline bg-card">
        <div
          className={cn(
            page,
            'flex min-h-16 flex-wrap items-center gap-x-8 gap-y-3 py-3 lg:min-h-[72px]',
          )}
        >
          <NavLink
            to="/"
            className="inline-flex min-h-12 items-center rounded-md text-[1.375rem] font-semibold leading-none tracking-tight text-accent"
          >
            {common.appName}
          </NavLink>
          <nav aria-label={common.mainNav} className="flex flex-wrap gap-1">
            {NAV[role].map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  cn(
                    'inline-flex min-h-12 items-center rounded-md px-4 text-sm font-semibold text-muted transition-colors hover:bg-sunken hover:text-ink',
                    isActive && 'bg-accent-soft text-accent hover:bg-accent-soft hover:text-accent',
                  )
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex w-full flex-wrap items-end gap-x-4 gap-y-3 sm:ml-auto sm:w-auto">
            <label className="flex flex-col gap-1 text-xs font-medium text-muted">
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
                {!preset && (
                  <option value="custom">
                    {formatDate(today)} ({common.customDate})
                  </option>
                )}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-muted">
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
            <p className="flex min-h-10 items-center text-sm">
              <span className="font-semibold">{user.name}</span>
            </p>
            <TextSizeToggle className="ml-auto sm:ml-0" />
          </div>
        </div>
        <p className="border-t border-hairline bg-accent-soft text-sm text-accent">
          <span className={cn(page, 'flex flex-wrap items-center gap-x-2 py-2')}>
            <CalendarClock aria-hidden className="h-4 w-4 shrink-0" />
            {common.simulatedDateBanner}:{' '}
            <strong className="font-semibold">{formatDate(today)}</strong>
          </span>
        </p>
      </header>
      <main id="main" tabIndex={-1} className={cn(page, 'py-8 pb-28 lg:py-12 lg:pb-28')}>
        <Outlet />
      </main>
      <footer className="fixed inset-x-0 bottom-0 z-10 border-t border-hairline bg-card/95 px-5 py-2 text-center text-xs text-muted backdrop-blur">
        {common.disclaimer}
      </footer>
    </div>
  )
}
