import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronRight,
  Copy,
  Download,
  FileText,
  LoaderCircle,
  RefreshCw,
  Sparkles,
  X,
} from 'lucide-react'
import { api } from '../lib/api'
import { markdownFor, stageLabel } from '../lib/summary'
import type { ArticleStatus, SummaryTask } from '../lib/types'
import { useToast } from '../context/ToastContext'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { MarkdownText } from './MarkdownText'

export function SummaryTaskView({
  task,
  variant = 'inline',
  onClose,
}: {
  task: SummaryTask
  variant?: 'inline' | 'reader' | 'page'
  onClose?: () => void
}) {
  const { pushToast } = useToast()
  const { retryTask, loadTask } = useSummaryQueue()
  const [tab, setTab] = useState<'summary' | 'article'>('summary')
  const [article, setArticle] = useState('')
  const [articleLoading, setArticleLoading] = useState(false)
  const [articleError, setArticleError] = useState<string | null>(null)
  const [resultError, setResultError] = useState<string | null>(null)
  const resultRequested = useRef(false)

  useEffect(() => {
    if (task.status !== 'done' || task.result || resultRequested.current) return
    resultRequested.current = true
    void loadTask(task.id)
      .catch((caught: unknown) => {
        setResultError(
          caught instanceof Error ? caught.message : '总结结果读取失败。',
        )
      })
  }, [task.id, task.result, task.status, loadTask])

  useEffect(() => {
    if (task.articleStatus !== 'done') return
    let cancelled = false
    // oxlint-disable-next-line react/set-state-in-effect -- loading state belongs to the fetch lifecycle
    setArticleLoading(true)
    setArticleError(null)
    void api
      .getArticle(task.id)
      .then((data) => {
        if (cancelled) return
        setArticle(data.article ?? '')
        setArticleError(data.error)
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        setArticleError(
          caught instanceof Error ? caught.message : '整理稿读取失败。',
        )
      })
      .finally(() => {
        if (!cancelled) setArticleLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [task.articleStatus, task.id])

  const retryArticle = useCallback(async () => {
    setArticleError(null)
    try {
      await api.createArticle(task.id)
      await loadTask(task.id)
    } catch (caught) {
      setArticleError(
        caught instanceof Error ? caught.message : '整理稿生成失败。',
      )
    }
  }, [loadTask, task.id])

  const retryResult = useCallback(async () => {
    setResultError(null)
    try {
      await loadTask(task.id)
    } catch (caught) {
      setResultError(
        caught instanceof Error ? caught.message : '总结结果读取失败。',
      )
    }
  }, [loadTask, task.id])

  const retrySummary = useCallback(async () => {
    try {
      await retryTask(task.id)
    } catch (caught) {
      pushToast(
        caught instanceof Error ? caught.message : '重试失败，请稍后重试。',
        'error',
      )
    }
  }, [pushToast, retryTask, task.id])

  const copySummary = async () => {
    if (!task.result) return
    try {
      await navigator.clipboard.writeText(markdownFor(task.result))
      pushToast('总结已复制为 Markdown。', 'success')
    } catch {
      pushToast('复制失败，请手动选择文本。', 'info')
    }
  }

  const copyArticle = async () => {
    if (!article) return
    try {
      await navigator.clipboard.writeText(article)
      pushToast('整理稿已复制为 Markdown。', 'success')
    } catch {
      pushToast('复制失败，请手动选择文本。', 'info')
    }
  }

  const downloadArticle = () => {
    if (!article) return
    const blob = new Blob([article], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${task.title || '视频整理稿'}.md`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  const summary = task.result
  const summaryActive =
    task.status === 'analyzing' ||
    task.status === 'queued' ||
    task.status === 'processing' ||
    task.status === 'cancelling'
  const summaryDone = task.status === 'done' && Boolean(summary)
  const articleBusy = task.articleStatus === 'processing' || articleLoading
  const articleStatus: ArticleStatus = task.articleStatus ?? 'idle'
  const articlePercent = Math.max(task.articleProgress ?? 0, 2)
  const isPage = variant === 'page'

  return (
    <section
      className={`summary-panel ${variant === 'reader' ? 'summary-panel--reader' : ''} ${isPage ? 'summary-panel--page' : ''}`}
      aria-live="polite"
    >
      <div className="summary-head">
        <div>
          <div className="summary-kicker">
            <Sparkles size={13} /> AI SUMMARY / 视频总结
          </div>
          <h3>{isPage ? task.title : '这段视频讲了什么？'}</h3>
          {isPage ? (
            <div className="summary-page-meta">
              <span>{task.platform || '视频平台'}</span>
              {task.uploader ? <span>· {task.uploader}</span> : null}
              {task.duration ? (
                <span>· {Math.floor(task.duration / 60)} 分钟</span>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="summary-head-actions">
          <a className="summary-task-link" href={`#/tasks/${task.id}`}>
            任务中心
          </a>
          {onClose ? (
            <button className="icon-btn" type="button" onClick={onClose} aria-label="关闭总结">
              <X size={17} />
            </button>
          ) : null}
        </div>
      </div>

      {summaryActive && (
        <div className="summary-progress">
          <div className="summary-progress-head">
            <span>
              <LoaderCircle className="spin" size={14} />
              {stageLabel(task.stage)}
            </span>
            <strong>{Math.round(task.progress || 0)}%</strong>
          </div>
          <div className="summary-progress-bar">
            <i style={{ width: `${Math.max(task.progress || 0, 3)}%` }} />
          </div>
          <p>
            {task.queuePosition
              ? `前面还有 ${task.queuePosition} 个任务在排队。`
              : task.stage === 'waiting_transcription' &&
                  task.transcribeQueuePosition
                ? `等待转写槽位，前面还有 ${task.transcribeQueuePosition} 个。`
                : task.transcriptSource === 'subtitle'
                  ? '已找到字幕，正在整理内容。'
                  : '无字幕时会在本地提取音频并转写，首次可能较慢。'}
          </p>
          <div className="summary-stage-dots" aria-hidden="true">
            <span className={task.stage === 'fetching_subtitles' ? 'active' : ''}>
              字幕
            </span>
            <span className={task.stage === 'downloading_audio' ? 'active' : ''}>
              音频
            </span>
            <span
              className={
                task.stage === 'transcribing' ||
                task.stage === 'waiting_transcription'
                  ? 'active'
                  : ''
              }
            >
              转写
            </span>
            <span className={task.stage === 'summarizing' ? 'active' : ''}>总结</span>
          </div>
          {task.canCancel ? (
            <p className="summary-progress-hint">
              可以关掉这个面板或去解析下一个视频，任务会在任务中心继续。
            </p>
          ) : null}
        </div>
      )}

      {task.status === 'error' && (
        <div className="summary-error">
          <AlertTriangle size={15} />
          <span>{task.error || 'AI 总结失败，请稍后重试。'}</span>
          {task.canRetry ? (
            <button type="button" onClick={() => void retrySummary()}>
              重试 <RefreshCw size={12} />
            </button>
          ) : null}
        </div>
      )}

      {task.status === 'cancelled' && (
        <div className="summary-error summary-cancelled">
          <AlertTriangle size={15} />
          <span>任务已取消，可以重新开始。</span>
          {task.canRetry ? (
            <button type="button" onClick={() => void retrySummary()}>
              重试 <RefreshCw size={12} />
            </button>
          ) : null}
        </div>
      )}

      {resultError && (
        <div className="summary-error">
          <AlertTriangle size={15} />
          <span>{resultError}</span>
          <button type="button" onClick={() => void retryResult()}>
            重试 <RefreshCw size={12} />
          </button>
        </div>
      )}

      {task.status === 'done' && !summary && !resultError && task.hasResult === false && (
        <div className="summary-cancelled">
          这次总结的结果已过期。可以打开笔记仓库查看已保存的 Markdown，或重新生成。
        </div>
      )}

      {task.status === 'done' && !summary && !resultError && task.hasResult !== false && (
        <div className="summary-progress">
          <div className="summary-progress-head">
            <span>
              <LoaderCircle className="spin" size={14} /> 正在读取总结结果
            </span>
          </div>
        </div>
      )}

      {summaryDone && (
        <div className="summary-tabs" role="tablist" aria-label="视频资料">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'summary'}
            className={tab === 'summary' ? 'active' : ''}
            onClick={() => setTab('summary')}
          >
            总结
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'article'}
            className={tab === 'article' ? 'active' : ''}
            onClick={() => setTab('article')}
          >
            完整文案
            {articleBusy
              ? ' · 整理中'
              : articleStatus === 'done'
                ? ' · 已就绪'
                : ''}
          </button>
        </div>
      )}

      {summaryDone && tab === 'summary' && summary && (
        <div className="summary-result">
          <div className="summary-meta">
            <span>{stageLabel('done')}</span>
            <span>·</span>
            <span>{task.transcriptSource === 'subtitle' ? '字幕整理' : '语音转写'}</span>
            {summary.model ? (
              <>
                <span>·</span>
                <span>{summary.model}</span>
              </>
            ) : null}
          </div>

          {task.noteId ? (
            <a className="note-saved-link" href={`#/library/${task.noteId}`}>
              <FileText size={13} /> 已存入笔记仓库 · 查看 Markdown
            </a>
          ) : null}

          {summary.fallback ? (
            <div className="summary-fallback">
              AI 这次没有返回完整结构，已降级为简要总结。可以点「重试」重新生成完整要点和章节。
            </div>
          ) : null}
          <div className="summary-tldr">{summary.tldr}</div>

          {summary.keyPoints.length ? (
            <div className="summary-block">
              <h4>核心要点</h4>
              <ul>
                {summary.keyPoints.map((point) => (
                  <li key={point}>
                    <Check size={13} /> {point}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {summary.chapters.length ? (
            <div className="summary-block">
              <h4>章节</h4>
              <div className="summary-chapters">
                {summary.chapters.map((chapter) => (
                  <div className="summary-chapter" key={`${chapter.time}-${chapter.title}`}>
                    <span>{chapter.time}</span>
                    <div>
                      <strong>{chapter.title}</strong>
                      <p>{chapter.summary}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {summary.quotes.length ? (
            <div className="summary-block">
              <h4>关键引用</h4>
              {summary.quotes.map((quote) => (
                <blockquote key={quote}>{quote}</blockquote>
              ))}
            </div>
          ) : null}

          <div className="summary-bottom">
            {summary.keywords.length ? (
              <div className="summary-keywords">
                {summary.keywords.map((keyword) => (
                  <span key={keyword}>{keyword}</span>
                ))}
              </div>
            ) : (
              <span />
            )}
            <button type="button" className="small-btn" onClick={() => void copySummary()}>
              <Copy size={13} /> 复制 Markdown
            </button>
          </div>
          <p className="summary-disclaimer">AI 生成，可能存在误差，请以原视频为准。</p>

          <div className="summary-next">
            <button type="button" className="small-btn" onClick={() => setTab('article')}>
              <FileText size={13} /> 查看完整文案
              <ChevronRight size={12} />
            </button>
          </div>
        </div>
      )}

      {summaryDone && tab === 'article' && (
        <div className="article-panel">
          {articleBusy && (
            <div className="summary-progress">
              <div className="summary-progress-head">
                <span>
                  <LoaderCircle className="spin" size={14} />
                  正在整理完整文案
                </span>
                <strong>{Math.round(articlePercent)}%</strong>
              </div>
              <div className="summary-progress-bar">
                <i style={{ width: `${articlePercent}%` }} />
              </div>
              <p>总结已经可用；整理稿会把完整转写改写成可读文章，请稍等。</p>
            </div>
          )}

          {articleError && !articleBusy && (
            <div className="summary-error">
              <AlertTriangle size={15} />
              <span>{articleError}</span>
              <button type="button" onClick={() => void retryArticle()}>
                重新整理 <RefreshCw size={12} />
              </button>
            </div>
          )}

          {articleStatus === 'done' && article && (
            <>
              <div className="article-meta">
                <span>
                  <FileText size={13} /> 完整文案
                </span>
                <span>{article.length.toLocaleString('zh-CN')} 字符</span>
              </div>
              <MarkdownText source={article} className="article-body" />
              <div className="article-actions">
                <button type="button" className="small-btn" onClick={() => void copyArticle()}>
                  <Copy size={13} /> 复制全文
                </button>
                <button type="button" className="small-btn ghost" onClick={downloadArticle}>
                  <Download size={13} /> 下载 .md
                </button>
              </div>
              <p className="summary-disclaimer">
                AI 根据字幕/转写整理，可能存在误差；完整内容请以原视频为准。
              </p>
            </>
          )}

          {articleStatus === 'cancelled' && !articleBusy && (
            <div className="article-empty">
              <FileText size={20} />
              <p>{task.articleError || '整理稿生成已取消。'}</p>
              <button type="button" className="small-btn" onClick={() => void retryArticle()}>
                <Sparkles size={13} /> 重新整理
              </button>
            </div>
          )}

          {articleStatus === 'idle' && !articleBusy && (
            <div className="article-empty">
              <FileText size={20} />
              <p>把完整转写整理成有标题、有段落的可读文案。</p>
              <button type="button" className="small-btn" onClick={() => void retryArticle()}>
                <Sparkles size={13} /> 生成完整文案
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
