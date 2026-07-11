import { BarChart3, ClipboardList } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { cn } from '../../lib/utils'

const links = [
  { to: '/review', label: 'Review Queue', icon: ClipboardList },
  { to: '/timeline', label: 'Timeline', icon: BarChart3 },
]

export function AppShell() {
  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
      <header className="glass-card mb-6 overflow-hidden">
        <div className="flex flex-col gap-6 border-b border-white/60 bg-[linear-gradient(120deg,rgba(13,92,109,0.92),rgba(17,57,69,0.9))] px-6 py-6 text-white md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-amber-200">
              Slack Event Manager
            </p>
            <h1 className="text-4xl text-white md:text-5xl">Operations review cockpit</h1>
            <p className="max-w-xl text-sm text-slate-100/80 md:text-base">
              Review extracted events, publish the validated signal, and inspect the company timeline from a single workspace.
            </p>
          </div>
          <nav className="flex flex-wrap gap-2">
            {links.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    'inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition',
                    isActive
                      ? 'bg-amber-300 text-slate-950 shadow-soft'
                      : 'bg-white/10 text-white hover:bg-white/20',
                  )
                }
              >
                <Icon className="size-4" />
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 pb-8">
        <Outlet />
      </main>
    </div>
  )
}