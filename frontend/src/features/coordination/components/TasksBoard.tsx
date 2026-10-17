import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useDemo } from '@/app/DemoContext'
import { BatonHolder } from '@/components/BatonHolder'
import { EmptyState, ErrorState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/Skeleton'
import { Button } from '@/components/ui/button'
import { coordination as t } from '@/i18n/cs/coordination'
import { problemTitle } from '@/lib/api/problem'
import { formatDate } from '@/lib/date'
import type { BatonHolderInfo } from '@/lib/domain'
import { useBoard, useTransitionTask, type Board, type BoardBaton, type BoardTask, type TransitionInput } from '../api'
import { LaunchPathway } from './LaunchPathway'
import { TaskCard } from './TaskCard'

/** The earlier of the planned date and the promised one: the date the API's overdue flag counts from. */
function earlier(a: string | null | undefined, b: string | null | undefined): string | null {
  if (!a || !b) return a ?? b ?? null
  return new Date(b) < new Date(a) ? b : a
}

/** Board baton as the shared BatonHolder component shows it; all texts come from the API's reason and task. */
function toBatonInfo(b: BoardBaton, task: BoardTask | undefined): BatonHolderInfo {
  return {
    name: b.owner?.display ?? t.lanes[b.role],
    action: t.baton[b.reason](b.task_title),
    due: earlier(b.due, task?.sla_due),
  }
}

function BoardView({ board, caseId }: { board: Board; caseId: string }) {
  const { role } = useDemo()
  const transition = useTransitionTask()
  const tasks = board.lanes.flatMap((l) => l.tasks)
  const titles = Object.fromEntries(tasks.map((x) => [x.id, x.title]))
  const batonTask = board.baton_holder ? tasks.find((x) => x.id === board.baton_holder?.task_id) : undefined
  const canAct = role === 'coordinator'
  const run = (input: TransitionInput, done: () => void) => transition.mutate(input, { onSuccess: done })

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <BatonHolder
          baton={board.baton_holder ? toBatonInfo(board.baton_holder, batonTask) : null}
          overdue={batonTask?.overdue}
          now={board.computed_at}
        />
        <p className="text-sm text-muted">{t.asOf(formatDate(board.computed_at))}</p>
      </div>
      {transition.isError && (
        <p role="alert" className="text-sm text-missing">
          {t.transitionError} {problemTitle(transition.error)}
        </p>
      )}
      <div role="group" aria-label={t.board} className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {board.lanes.map((lane) => (
          <section key={lane.role} aria-labelledby={`lane-${lane.role}`} className="space-y-2 rounded-lg bg-accent-soft/40 p-3">
            <h3 id={`lane-${lane.role}`} className="text-base">
              {t.lanes[lane.role]}
            </h3>
            {lane.tasks.length === 0 && <p className="text-sm text-muted">{t.laneEmpty}</p>}
            <ul className="space-y-2">
              {lane.tasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  titles={titles}
                  now={board.computed_at}
                  caseId={caseId}
                  canAct={canAct}
                  busy={transition.isPending}
                  onTransition={run}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  )
}

/** Demo step 4: launch the pathway with the indicating physician, then see who holds the baton in each lane. */
export function TasksTab() {
  const { id = '' } = useParams()
  const { role } = useDemo()
  const q = useBoard(id)
  const [launching, setLaunching] = useState(false)
  const hasTasks = q.data?.lanes.some((l) => l.tasks.length > 0) ?? false

  return (
    <section aria-label={t.title} className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl">{t.title}</h2>
        {q.isSuccess && !hasTasks && !launching && (
          <Button variant="primary" disabled={role !== 'coordinator'} onClick={() => setLaunching(true)}>
            {t.launch.open}
          </Button>
        )}
      </div>
      {q.isPending && <LoadingBlock />}
      {q.isError && <ErrorState onRetry={() => void q.refetch()} />}
      {q.isSuccess && !hasTasks && !launching && <EmptyState title={t.empty} hint={t.emptyHint} />}
      {launching && !hasTasks && <LaunchPathway caseId={id} onClose={() => setLaunching(false)} />}
      {q.isSuccess && hasTasks && <BoardView board={q.data} caseId={id} />}
    </section>
  )
}
