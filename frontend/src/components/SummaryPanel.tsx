import { useState } from 'react'
import { AlertTriangle, ChevronRight, LoaderCircle, Sparkles, X } from 'lucide-react'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { useToast } from '../context/ToastContext'
import { isTaskActive, taskStatusLabel } from '../lib/summary'
import type { AnalyzeResult } from '../lib/types'
import { SummaryTaskView } from './SummaryTaskView'

export function SummaryPanel({
  result,
  variant = 'inline',
}: {
  result: AnalyzeResult
  variant?: 'inline' | 'reader'
}) {
  const { pushToast } = useToast()
  const { enqueueOne, findByUrl, getTask } = useSummaryQueue()
  const [open, setOpen] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const existing = findByUrl(result.webpageUrl)
  const task = taskId ? getTask(taskId) : existing

  const handleTrigger = async () => {
    setOpen(true)
    setError(null)
    if (existing) {
      setTaskId(existing.id)
      return
    }
    setStarting(true)
    try {
      const created = await enqueueOne(result)
      setTaskId(created.id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'AI 总结暂时不可用。')
    } finally {
      setStarting(false)
    }
  }

  const close = () => {
    setOpen(false)
    if (task && isTaskActive(task)) {
      pushToast('已转入任务中心，任务会继续处理。', 'info')
    }
  }

  if (!open) {
    return (
      <button
        className={`summary-trigger ${variant === 'reader' ? 'summary-trigger--reader' : ''}`}
        type="button"
        onClick={() => void handleTrigger()}
      >
        <span className="summary-trigger-icon">
          <Sparkles size={18} />
        </span>
        <span className="summary-trigger-copy">
          <strong>{existing?.status === 'done' ? '查看 AI 总结' : 'AI 视频总结'}</strong>
          <small>
            {existing
              ? `任务中心 · ${taskStatusLabel(existing.status)}`
              : '字幕优先 · 无字幕自动转写'}
          </small>
        </span>
        <ChevronRight size={16} className="summary-trigger-arrow" />
      </button>
    )
  }

  if (task) {
    return (
      <SummaryTaskView
        key={task.id}
        task={task}
        variant={variant}
        onClose={close}
      />
    )
  }

  return (
    <section
      className={`summary-panel ${variant === 'reader' ? 'summary-panel--reader' : ''}`}
    >
      <div className="summary-head">
        <div>
          <div className="summary-kicker">
            <Sparkles size={13} /> AI SUMMARY / 视频总结
          </div>
          <h3>这段视频讲了什么？</h3>
        </div>
        <button className="icon-btn" type="button" onClick={close} aria-label="关闭总结">
          <X size={17} />
        </button>
      </div>

      {starting && !error ? (
        <div className="summary-progress">
          <div className="summary-progress-head">
            <span>
              <LoaderCircle className="spin" size={14} /> 正在加入任务队列
            </span>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="summary-error">
          <AlertTriangle size={15} />
          <span>{error}</span>
          <button type="button" onClick={() => void handleTrigger()}>
            重试
          </button>
        </div>
      ) : null}
    </section>
  )
}
