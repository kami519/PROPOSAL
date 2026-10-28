import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  LoaderCircle,
  Play,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { useToast } from '../context/ToastContext'
import { secondsToClock } from '../lib/format'
import { isTaskActive, stageLabel, taskStatusLabel } from '../lib/summary'
import type { SummaryTask } from '../lib/types'

function statusTone(task: SummaryTask): string {
  if (task.status === 'done') return 'ok'
  if (task.status === 'error') return 'error'
  if (task.status === 'cancelled') return 'muted'
  if (task.status === 'cancelling') return 'working'
  if (task.status === 'analyzing') return 'working'
  return 'working'
}

function statusText(task: SummaryTask): string {
  if (task.status === 'processing') return stageLabel(task.stage)
  if (task.status === 'done' && task.articleStatus === 'processing') {
    return '文案整理中'
  }
  return taskStatusLabel(task.status)
}

export function TaskCard({ task }: { task: SummaryTask }) {
  const { pushToast } = useToast()
  const { cancelTask, retryTask, dismissTask } = useSummaryQueue()
  const [busy, setBusy] = useState(false)
  const isLocal = task.id.startsWith('local_')
  const active = isTaskActive(task)
  const tone = statusTone(task)
  const percent = Math.round(task.progress || 0)

  const cancel = async () => {
    if (!window.confirm('取消后，已产生的临时内容会被清理。确定取消吗？')) return
    setBusy(true)
    try {
      await cancelTask(task.id)
      pushToast('已取消任务。', 'info')
    } catch (caught) {
      pushToast(
        caught instanceof Error ? caught.message : '取消失败，请稍后重试。',
        'error',
      )
    } finally {
      setBusy(false)
    }
  }

  const retry = async () => {
    setBusy(true)
    try {
      await retryTask(task.id)
      pushToast('已重新加入队列。', 'success')
    } catch (caught) {
      pushToast(
        caught instanceof Error ? caught.message : '重试失败，请稍后重试。',
        'error',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className={`task-card task-card--${tone}`}>
      <div className="task-card-cover">
        {task.thumbnail ? (
          <img src={task.thumbnail} alt="" referrerPolicy="no-referrer" loading="lazy" />
        ) : (
          <span className="task-cover-placeholder">
            {task.status === 'analyzing' ? (
              <LoaderCircle className="spin" size={20} />
            ) : (
              <Play size={20} fill="currentColor" strokeWidth={0} />
            )}
          </span>
        )}
        <span className={`task-status task-status--${tone}`}>
          {active ? <LoaderCircle className="spin" size={11} /> : null}
          {task.status === 'done' ? <CheckCircle2 size={11} /> : null}
          {task.status === 'error' ? <AlertTriangle size={11} /> : null}
          {task.status === 'cancelled' ? <XCircle size={11} /> : null}
          {statusText(task)}
        </span>
      </div>

      <div className="task-card-body">
        <div className="task-card-heading">
          <h3>
            {isLocal || task.status === 'analyzing' ? (
              <span className="task-local-title">解析视频信息…</span>
            ) : (
              <a href={`#/tasks/${task.id}`}>{task.title || '未命名视频'}</a>
            )}
          </h3>
          <span className="task-card-percent">
            {task.status === 'processing' ? `${percent}%` : ''}
          </span>
        </div>

        <div className="task-card-meta">
          {task.platform ? <span>{task.platform}</span> : null}
          {task.uploader ? <span>{task.uploader}</span> : null}
          {task.duration ? <span>{secondsToClock(task.duration)}</span> : null}
          {task.articleStatus === 'processing' ? <span>文案整理中</span> : null}
          {task.articleStatus === 'done' ? <span>文案已就绪</span> : null}
        </div>

        {task.status === 'analyzing' ? (
          <p className="task-card-note">正在解析标题、封面和时长，解析完会自动入队。</p>
        ) : null}

        {active && task.status !== 'analyzing' ? (
          <>
            <div className="task-progress" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
              <i style={{ width: `${Math.max(percent, 3)}%` }} />
            </div>
            {task.queuePosition ? (
              <p className="task-queue-hint">排队第 {task.queuePosition} 位</p>
            ) : task.transcribeQueuePosition ? (
              <p className="task-queue-hint">
                等待转写，前面还有 {task.transcribeQueuePosition} 个
              </p>
            ) : null}
          </>
        ) : null}

        {task.tldr ? <p className="task-tldr">{task.tldr}</p> : null}
        {task.error ? <p className="task-error">{task.error}</p> : null}
        {task.localError && task.localError !== task.error ? (
          <p className="task-error">{task.localError}</p>
        ) : null}

        <div className="task-card-actions">
          {!isLocal && task.status !== 'analyzing' ? (
            <a className="small-btn" href={`#/tasks/${task.id}`}>
              详情
            </a>
          ) : null}
          {task.noteId ? (
            <a className="small-btn" href={`#/library/${task.noteId}`}>
              <FileText size={12} /> 笔记
            </a>
          ) : null}
          {task.canCancel && (task.status !== 'analyzing' || isLocal) ? (
            <button type="button" className="small-btn danger" onClick={() => void cancel()} disabled={busy}>
              取消
            </button>
          ) : null}
          {(task.canRetry || task.status === 'error' || task.status === 'cancelled') &&
          !active ? (
            <button type="button" className="small-btn primary" onClick={() => void retry()} disabled={busy}>
              <RefreshCw size={12} /> 重试
            </button>
          ) : null}
          {!active ? (
            <button type="button" className="small-btn ghost" onClick={() => dismissTask(task.id)} disabled={busy}>
              <Trash2 size={12} /> 清理
            </button>
          ) : null}
        </div>
      </div>
    </article>
  )
}
