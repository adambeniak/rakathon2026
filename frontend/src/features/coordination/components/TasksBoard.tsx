import { useParams } from 'react-router-dom'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { useDemo } from '@/app/DemoContext'
import { cases as t } from '@/i18n/cs/cases'
import { cn } from '@/lib/cn'
import { daysUntil, formatDate, formatRemaining } from '@/lib/date'
import { TASK_LANES, TASK_PHASES, type TaskItem, type TaskPhase } from '@/lib/domain'
import { useAdvanceTask, useStartTaskSet, useTasks } from '../api'

const nextPhase = (p: TaskPhase): Exclude<TaskPhase, 'to_order'> | null => {
  const n = TASK_PHASES[TASK_PHASES.indexOf(p) + 1]
  return n && n !== 'to_order' ? n : null
}

function TaskCard({ task, all, busy, canAct, onAdvance }: { task: TaskItem; all: TaskItem[]; busy: boolean; canAct: boolean; onAdvance: (p: TaskPhase) => void }) {
  const { today } = useDemo()
  const blocker = task.dependsOn.map((d) => all.find((x) => x.id === d)).find((d) => d && d.state !== 'done')
  const next = nextPhase(task.phase)
  const overdue = task.state === 'overdue'
  const days = daysUntil(task.due, today)
  return (
    <li className={cn('space-y-1.5 rounded border bg-card p-3 text-sm', overdue ? 'border-missing/60' : 'border-hairline')}>
      <p className="font-medium">{task.title}</p>
      <p className="text-muted">
        {t.tasks.place}: {task.place}
      </p>
      <p className={cn(overdue && 'font-semibold text-missing')}>
        {t.tasks.due} {formatDate(task.due)}
        {task.state !== 'done' && ` (${formatRemaining(days)})`}
        {overdue && <span className="ml-2 rounded bg-missing-bg px-1.5 py-0.5 text-xs">{t.tasks.state.overdue}</span>}
      </p>
      <p className="text-xs font-medium text-accent">{t.tasks.phase[task.phase]}</p>
      {blocker && <p className="text-xs text-conflict">{t.tasks.blockedBy(blocker.title)}</p>}
      {next && (
        <Button
          variant="secondary"
          disabled={!canAct || busy || !!blocker}
          onClick={() => onAdvance(next)}
          aria-label={t.tasks.actionAria(t.tasks.action[next], task.title)}
        >
          {t.tasks.action[next]}
        </Button>
      )}
    </li>
  )
}

/** Demo step 4: start the task set, then see who holds the baton in each lane. */
export function TasksTab() {
  const { id = '' } = useParams()
  const { role } = useDemo()
  const q = useTasks(id)
  const start = useStartTaskSet(id)
  const advance = useAdvanceTask(id)
  const canAct = role === 'coordinator'

  return (
    <section aria-label={t.tasks.title} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl">{t.tasks.title}</h2>
        {q.data?.length === 0 && (
          <Button variant="primary" disabled={!canAct || start.isPending} onClick={() => start.mutate()}>
            {start.isPending ? t.tasks.starting : t.tasks.startSet}
          </Button>
        )}
      </div>
      {q.isPending && <LoadingBlock />}
      {q.isError && <ErrorState onRetry={() => void q.refetch()} />}
      {q.data?.length === 0 && <EmptyState title={t.tasks.empty} hint={t.tasks.emptyHint} />}
      {(start.isError || advance.isError) && (
        <p role="alert" className="text-sm text-missing">
          {t.tasks.error}
        </p>
      )}
      {q.data && q.data.length > 0 && (
        <div role="group" aria-label={t.tasks.board} className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {TASK_LANES.map((lane) => {
            const items = q.data.filter((x) => x.lane === lane)
            return (
              <section key={lane} aria-labelledby={`lane-${lane}`} className="space-y-2 rounded-lg bg-accent-soft/40 p-3">
                <h3 id={`lane-${lane}`} className="text-base">
                  {t.tasks.lanes[lane]}
                </h3>
                {items.length === 0 && <p className="text-sm text-muted">{t.tasks.laneEmpty}</p>}
                <ul className="space-y-2">
                  {items.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      all={q.data}
                      busy={advance.isPending}
                      canAct={canAct}
                      onAdvance={(phase) => advance.mutate({ taskId: task.id, phase })}
                    />
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </section>
  )
}
