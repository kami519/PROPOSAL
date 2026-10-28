import { useMemo, useState } from 'react'
import {
  ArrowLeft,
  Bell,
  BellOff,
  Inbox,
  LoaderCircle,
  RefreshCw,
} from 'lucide-react'
import { BatchSummary } from '../components/BatchSummary'
import { TaskCard } from '../components/TaskCard'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { isTaskActive } from '../lib/summary'
import type { SummaryTask } from '../lib/types'

type Filter = 'all' | 'active' | 'done' | 'error' | 'cancelled'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: '全部' },
  { id: 'active', label: '进行中' },
  { id: 'done', label: '已完成' },
  { id: 'error', label: '失败' },
  { id: 'cancelled', label: '已取消' },
]

function matches(task: SummaryTask, filter: Filter): boolean {
  if (filter === 'all') return true
  if (filter === 'active') return isTaskActive(task)
  if (filter === 'done') return task.status === 'done'
  if (filter === 'error') return task.status === 'error'
  return task.status === 'cancelled'
}

function isToday(timestamp: number | null | undefined): boolean {
  if (!timestamp) return false
  const date = new Date(timestamp * 1000)
  const now = new Date()
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  )
}

export function TaskCenterPage() {
  const {
    tasks,
    activeCount,
    notificationsEnabled,
    toggleNotifications,
    refresh,
  } = useSummaryQueue()
  const [filter, setFilter] = useState<Filter>('all')
  const [refreshing, setRefreshing] = useState(false)

  const counts = useMemo(
    () => ({
      all: tasks.length,
      active: tasks.filter((task) => isTaskActive(task)).length,
      done: tasks.filter((task) => task.status === 'done').length,
      error: tasks.filter((task) => task.status === 'error').length,
      cancelled: tasks.filter((task) => task.status === 'cancelled').length,
    }),
    [tasks],
  )

  const visible = useMemo(() => {
    return tasks
      .filter((task) => matches(task, filter))
      .sort((left, right) => {
        const leftActive = isTaskActive(left) ? 1 : 0
        const rightActive = isTaskActive(right) ? 1 : 0
        if (leftActive !== rightActive) return rightActive - leftActive
        return (right.updatedAt || 0) - (left.updatedAt || 0)
      })
  }, [filter, tasks])

  const queued = tasks.filter(
    (task) => task.status === 'queued' || task.status === 'analyzing',
  ).length
  const doneToday = tasks.filter(
    (task) => task.status === 'done' && isToday(task.finishedAt),
  ).length

  const doRefresh = async () => {
    setRefreshing(true)
    try {
      await refresh()
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="tasks-page">
      <div className="tasks-head">
        <div>
          <div className="tasks-kicker">TASKS / 任务中心</div>
          <h1>多个视频，同时整理。</h1>
          <p>任务在后台并行处理，关掉页面再回来也能接着看。</p>
        </div>
        <a className="tasks-back" href="#top">
          <ArrowLeft size={14} /> 回到收片
        </a>
      </div>

      <div className="tasks-stats" aria-label="任务统计">
        <div>
          <strong>{activeCount}</strong>
          <span>并行中</span>
        </div>
        <div>
          <strong>{queued}</strong>
          <span>排队中</span>
        </div>
        <div>
          <strong>{doneToday}</strong>
          <span>今日完成</span>
        </div>
        <div>
          <strong>{counts.error}</strong>
          <span>失败</span>
        </div>
      </div>

      <BatchSummary />

      <div className="tasks-toolbar">
        <div className="task-filters" role="tablist" aria-label="筛选任务">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={filter === item.id}
              className={filter === item.id ? 'active' : ''}
              onClick={() => setFilter(item.id)}
            >
              {item.label}
              <span>{counts[item.id]}</span>
            </button>
          ))}
        </div>
        <div className="tasks-toolbar-actions">
          <button
            type="button"
            className="library-small-btn"
            onClick={() => void toggleNotifications()}
            aria-pressed={notificationsEnabled}
          >
            {notificationsEnabled ? <Bell size={14} /> : <BellOff size={14} />}
            {notificationsEnabled ? '桌面通知已开' : '桌面通知'}
          </button>
          <button
            type="button"
            className="library-small-btn primary"
            onClick={() => void doRefresh()}
            disabled={refreshing}
          >
            {refreshing ? (
              <LoaderCircle className="spin" size={14} />
            ) : (
              <RefreshCw size={14} />
            )}
            刷新
          </button>
        </div>
      </div>

      {visible.length ? (
        <div className="task-grid">
          {visible.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))}
        </div>
      ) : (
        <div className="tasks-empty">
          <div className="tasks-empty-icon">
            <Inbox size={26} />
          </div>
          <h2>{tasks.length ? '这个筛选下没有任务' : '队列还是空的'}</h2>
          <p>
            {tasks.length
              ? '换个筛选条件试试。'
              : '在上面粘贴一个或多个视频链接，后台会并行总结。'}
          </p>
          {!tasks.length ? (
            <a className="library-small-btn primary" href="#top">
              去首页收片
            </a>
          ) : null}
        </div>
      )}
    </div>
  )
}
