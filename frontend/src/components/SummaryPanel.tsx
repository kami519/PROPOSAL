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
import type {
  AnalyzeResult,
  ArticleStatus,
  SummaryJob,
  SummaryResult,
} from '../lib/types'
import { useToast } from '../context/ToastContext'
import { MarkdownText } from './MarkdownText'

const STAGE_LABELS: Record<string, string> = {
  queued: '排队中',
  fetching_subtitles: '提取字幕',
  downloading_audio: '提取音频',
  transcribing: '语音转写',
  summarizing: '生成总结',
  writing_article: '整理文案',
  done: '完成',
}

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] || '处理中'
}

function markdownFor(result: SummaryResult): string {
  const lines = [`## ${result.tldr}`, '']
  if (result.keyPoints.length) {
    lines.push('### 核心要点', '')
    result.keyPoints.forEach((point) => lines.push(`- ${point}`))
    lines.push('')
  }
  if (result.chapters.length) {
    lines.push('### 章节', '')
    result.chapters.forEach((chapter) =>
      lines.push(`- **${chapter.time} ${chapter.title}**：${chapter.summary}`),
    )
    lines.push('')
  }
  if (result.quotes.length) {
    lines.push('### 关键引用', '')
    result.quotes.forEach((quote) => lines.push(`> ${quote}`, ''))
  }
  if (result.keywords.length) {
    lines.push(`**关键词：** ${result.keywords.join('、')}`)
  }
  return lines.join('\n')
}

export function SummaryPanel({
  result,
  variant = 'inline',
}: {
  result: AnalyzeResult
  variant?: 'inline' | 'reader'
}) {
  const { pushToast } = useToast()
  const [open, setOpen] = useState(false)
  const [job, setJob] = useState<SummaryJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [tab, setTab] = useState<'summary' | 'article'>('summary')
  const [article, setArticle] = useState('')
  const [articleStatus, setArticleStatus] = useState<ArticleStatus>('idle')
  const [articleError, setArticleError] = useState<string | null>(null)
  const [articleLoading, setArticleLoading] = useState(false)
  const timer = useRef<number | null>(null)
  const generation = useRef(0)

  const stopPolling = useCallback(() => {
    generation.current += 1
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  const loadArticle = useCallback(async (id: string) => {
    setArticleLoading(true)
    try {
      const data = await api.getArticle(id)
      setArticleStatus(data.status)
      setArticle(data.article ?? '')
      setArticleError(data.error)
    } catch (caught) {
      setArticleStatus('error')
      setArticleError(caught instanceof Error ? caught.message : '整理稿读取失败。')
    } finally {
      setArticleLoading(false)
    }
  }, [])

  const poll = useCallback(
    (id: string) => {
      const current = ++generation.current
      const tick = async () => {
        if (current !== generation.current) return
        try {
          const next = await api.getSummary(id)
          if (current !== generation.current) return
          setJob(next)
          if (next.status === 'done') {
            setStarting(false)
            const nextArticle = next.articleStatus ?? 'idle'
            setArticleStatus(nextArticle)
            if (nextArticle === 'processing') {
              timer.current = window.setTimeout(tick, 1200)
              return
            }
            if (nextArticle === 'done') {
              void loadArticle(id)
              return
            }
            setArticleError(next.articleError ?? null)
            return
          }
          if (next.status === 'error') {
            setStarting(false)
            setError(next.error || 'AI 总结失败，请稍后重试。')
            return
          }
          timer.current = window.setTimeout(tick, 1000)
        } catch (caught) {
          if (current !== generation.current) return
          setStarting(false)
          setError(caught instanceof Error ? caught.message : '总结状态获取失败。')
        }
      }
      void tick()
    },
    [loadArticle],
  )

  const start = async () => {
    setOpen(true)
    setStarting(true)
    setError(null)
    setJob(null)
    setTab('summary')
    setArticle('')
    setArticleStatus('idle')
    setArticleError(null)
    try {
      const created = await api.createSummary(result)
      setJob(created)
      setArticleStatus(created.articleStatus ?? 'idle')
      if (created.status === 'error') {
        setStarting(false)
        setError(created.error || 'AI 总结失败，请稍后重试。')
        return
      }
      poll(created.id)
    } catch (caught) {
      setStarting(false)
      setError(caught instanceof Error ? caught.message : 'AI 总结暂时不可用。')
    }
  }

  const handleTrigger = () => {
    if (job) {
      setOpen(true)
      const nextArticle = job.articleStatus ?? 'idle'
      if (job.status !== 'done' && job.status !== 'error') poll(job.id)
      if (job.status === 'done' && nextArticle === 'processing') poll(job.id)
      if (job.status === 'done' && nextArticle === 'done') {
        void loadArticle(job.id)
      }
      return
    }
    void start()
  }

  const close = () => {
    stopPolling()
    setOpen(false)
    setStarting(false)
  }

  const retryArticle = async () => {
    if (!job) return
    setArticleError(null)
    setArticleStatus('processing')
    try {
      const next = await api.createArticle(job.id)
      setJob(next)
      poll(job.id)
    } catch (caught) {
      setArticleStatus('error')
      setArticleError(caught instanceof Error ? caught.message : '整理稿生成失败。')
    }
  }

  const copySummary = async () => {
    if (!job?.result) return
    try {
      await navigator.clipboard.writeText(markdownFor(job.result))
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
    anchor.download = `${result.title || '视频整理稿'}.md`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  if (!open) {
    return (
      <button
        className={`summary-trigger ${variant === 'reader' ? 'summary-trigger--reader' : ''}`}
        type="button"
        onClick={handleTrigger}
      >
        <span className="summary-trigger-icon">
          <Sparkles size={18} />
        </span>
        <span className="summary-trigger-copy">
          <strong>AI 视频总结</strong>
          <small>字幕优先 · 无字幕自动转写</small>
        </span>
        <ChevronRight size={16} className="summary-trigger-arrow" />
      </button>
    )
  }

  const summary = job?.result
  const summaryDone = job?.status === 'done' && Boolean(summary)
  const articleBusy = articleStatus === 'processing' || articleLoading
  const articlePercent = Math.max(job?.articleProgress ?? 0, 2)

  return (
    <section className={`summary-panel ${variant === 'reader' ? 'summary-panel--reader' : ''}`}>
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

      {(starting || (job && job.status !== 'done' && job.status !== 'error')) && (
        <div className="summary-progress">
          <div className="summary-progress-head">
            <span>
              <LoaderCircle className="spin" size={14} />
              {stageLabel(job?.stage || 'queued')}
            </span>
            <strong>{Math.round(job?.progress || 0)}%</strong>
          </div>
          <div className="summary-progress-bar">
            <i style={{ width: `${Math.max(job?.progress || 0, 3)}%` }} />
          </div>
          <p>
            {job?.transcriptSource === 'subtitle'
              ? '已找到字幕，正在整理内容。'
              : '无字幕时会在本地提取音频并转写，首次可能较慢。'}
          </p>
          <div className="summary-stage-dots" aria-hidden="true">
            <span className={job?.stage === 'fetching_subtitles' ? 'active' : ''}>字幕</span>
            <span className={job?.stage === 'downloading_audio' ? 'active' : ''}>音频</span>
            <span className={job?.stage === 'transcribing' ? 'active' : ''}>转写</span>
            <span className={job?.stage === 'summarizing' ? 'active' : ''}>总结</span>
          </div>
        </div>
      )}

      {error && (
        <div className="summary-error">
          <AlertTriangle size={15} />
          <span>{error}</span>
          <button type="button" onClick={() => void start()}>
            重试 <RefreshCw size={12} />
          </button>
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
            {articleBusy ? ' · 整理中' : articleStatus === 'done' ? ' · 已就绪' : ''}
          </button>
        </div>
      )}

      {summaryDone && tab === 'summary' && summary && (
        <div className="summary-result">
          <div className="summary-meta">
            <span>{stageLabel('done')}</span>
            <span>·</span>
            <span>{job.transcriptSource === 'subtitle' ? '字幕整理' : '语音转写'}</span>
            {summary.model ? (
              <>
                <span>·</span>
                <span>{summary.model}</span>
              </>
            ) : null}
          </div>

          {job.noteId ? (
            <a className="note-saved-link" href={`#/library/${job.noteId}`}>
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
