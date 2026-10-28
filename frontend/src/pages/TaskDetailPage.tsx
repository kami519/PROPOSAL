import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, ArrowLeft, LoaderCircle, RefreshCw, XCircle } from 'lucide-react'
import { SummaryTaskView } from '../components/SummaryTaskView'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { useToast } from '../context/ToastContext'
import { isTaskActive, taskStatusLabel } from '../lib/summary'

export function TaskDetailPage({ taskId }: { taskId: string }) {
  const { getTask, loadTask, cancelTask, retryTask } = useSummaryQueue()
  const { pushToast } = useToast()
  const task = getTask(taskId)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (task) return
    let cancelled = false
    void loadTask(taskId)
      .catch((caught: unknown) => {
        if (cancelled) return
        setError(
          caught instanceof Error ? caught.message : '任务不存在或已过期。',
        )
      })
    return () => {
      cancelled = true
    }
  }, [loadTask, task, taskId])

  const cancel = useCallback(async () => {
    if (!window.confirm('取消后，已产生的临时内容会被清理。确定取消吗？')) return
    setBusy(true)
    try {
      await cancelTask(taskId)
      pushToast('已取消任务。', 'info')
    } catch (caught) {
      pushToast(
        caught instanceof Error ? caught.message : '取消失败，请稍后重试。',
        'error',
      )
    } finally {
      setBusy(false)
    }
  }, [cancelTask, pushToast, taskId])

  const retry = useCallback(async () => {
    setBusy(true)
    try {
      await retryTask(taskId)
      pushToast('已重新加入队列。', 'success')
    } catch (caught) {
      pushToast(
        caught instanceof Error ? caught.message : '重试失败，请稍后重试。',
        'error',
      )
    } finally {
      setBusy(false)
    }
  }, [pushToast, retryTask, taskId])

  if (error) {
    return (
      <div className="tasks-page">
        <a className="tasks-back" href="#/tasks">
          <ArrowLeft size={14} /> 返回任务中心
        </a>
        <div className="tasks-empty">
          <div className="tasks-empty-icon">
            <AlertTriangle size={26} />
          </div>
          <h2>任务不存在或已过期</h2>
          <p>{error}</p>
          <button type="button" className="library-small-btn primary" onClick={() => window.location.reload()}>
            刷新页面
          </button>
        </div>
      </div>
    )
  }

  if (!task) {
    return (
      <div className="tasks-page">
        <div className="tasks-loading">
          <LoaderCircle className="spin" size={18} />
          <span>读取任务…</span>
        </div>
      </div>
    )
  }

  const active = isTaskActive(task)

  return (
    <div className="tasks-page task-detail-page">
      <div className="task-detail-top">
        <a className="tasks-back" href="#/tasks">
          <ArrowLeft size={14} /> 返回任务中心
        </a>
        <span className={`task-detail-status ${active ? 'working' : task.status}`}>
          {taskStatusLabel(task.status)}
        </span>
      </div>

      <SummaryTaskView key={task.id} task={task} variant="page" />

      <div className="task-detail-actions">
        {task.canCancel ? (
          <button
            type="button"
            className="library-small-btn danger"
            onClick={() => void cancel()}
            disabled={busy}
          >
            <XCircle size={14} /> {task.status === 'done' ? '取消文案整理' : '取消任务'}
          </button>
        ) : null}
        {task.status === 'error' || task.status === 'cancelled' ? (
          <button
            type="button"
            className="library-small-btn primary"
            onClick={() => void retry()}
            disabled={busy}
          >
            <RefreshCw size={14} /> 重试
          </button>
        ) : null}
        {task.noteId ? (
          <a className="library-small-btn" href={`#/library/${task.noteId}`}>
            打开笔记
          </a>
        ) : null}
        <a className="library-small-btn ghost" href="#top">
          继续收下一个
        </a>
      </div>
    </div>
  )
}
