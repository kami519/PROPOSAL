import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, ChevronRight, Link2, LoaderCircle, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { extractVideoUrl, isLikelyUrl } from '../lib/format'
import type { AnalyzeResult, FormatOption, Job, LoadPhase } from '../lib/types'
import { useToast } from '../context/ToastContext'
import { ResultWorkbench } from './ResultWorkbench'

const PLATFORMS = [
  { label: 'B站', color: '#fb7299' },
  { label: '抖音', color: '#161823' },
  { label: 'YouTube', color: '#ff0033' },
  { label: 'TikTok', color: '#25f4ee' },
  { label: '小红书', color: '#ff2442' },
  { label: 'X', color: '#0f1419' },
  { label: 'Instagram', color: '#e4405f' },
  { label: 'Vimeo', color: '#1ab7ea' },
]

export function Downloader({
  onResultChange,
}: {
  onResultChange?: (hasResult: boolean) => void
}) {
  const { pushToast } = useToast()

  const [url, setUrl] = useState('')
  const [activeUrl, setActiveUrl] = useState('')
  const [phase, setPhase] = useState<LoadPhase>('idle')
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [selected, setSelected] = useState<FormatOption | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [errorKind, setErrorKind] = useState<'analyze' | 'download' | null>(null)
  const [pasteBusy, setPasteBusy] = useState(false)

  const inputRef = useRef<HTMLInputElement>(null)
  const resultRef = useRef<HTMLDivElement>(null)
  const pollTimer = useRef<number | null>(null)
  const pollGeneration = useRef(0)
  const autoDownloaded = useRef(false)

  const stopPolling = useCallback(() => {
    pollGeneration.current += 1
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  useEffect(() => {
    onResultChange?.(Boolean(result))
  }, [result, onResultChange])

  const scrollToResult = useCallback(() => {
    if (window.innerWidth < 960) {
      window.setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 60)
    }
  }, [])

  const reset = useCallback(() => {
    stopPolling()
    setPhase('idle')
    setResult(null)
    setSelected(null)
    setJob(null)
    setError(null)
    setErrorKind(null)
    setActiveUrl('')
    autoDownloaded.current = false
  }, [stopPolling])

  const triggerBrowserDownload = useCallback((nextJob: Job) => {
    if (!nextJob.downloadUrl) return
    const anchor = document.createElement('a')
    anchor.href = nextJob.downloadUrl
    anchor.download = nextJob.filename || 'clipdock-video.mp4'
    anchor.style.display = 'none'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  }, [])

  const pollJob = useCallback(
    (jobId: string) => {
      const generation = ++pollGeneration.current
      const tick = async () => {
        if (generation !== pollGeneration.current) return
        try {
          const next = await api.getJob(jobId)
          if (generation !== pollGeneration.current) return
          setJob(next)
          if (next.status === 'done') {
            setPhase('done')
            if (!autoDownloaded.current) {
              autoDownloaded.current = true
              triggerBrowserDownload(next)
            }
            return
          }
          if (next.status === 'error') {
            setPhase('error')
            setError(next.error || '下载失败，请稍后重试。')
            setErrorKind('download')
            return
          }
          if (next.status === 'cancelled') {
            setPhase('cancelled')
            return
          }
          pollTimer.current = window.setTimeout(tick, 900)
        } catch (caught) {
          if (generation !== pollGeneration.current) return
          setPhase('error')
          setError(caught instanceof Error ? caught.message : '任务状态获取失败，请稍后重试。')
          setErrorKind('download')
        }
      }
      void tick()
    },
    [triggerBrowserDownload],
  )

  async function startDownload(format: FormatOption) {
    if (!result || !activeUrl) return
    stopPolling()
    autoDownloaded.current = false
    setSelected(format)
    setJob(null)
    setError(null)
    setErrorKind(null)
    setPhase('downloading')
    try {
      const created = await api.createJob(
        activeUrl,
        format.id,
        {
          title: result.title,
          thumbnail: result.thumbnail,
          platform: result.platform,
        },
      )
      setJob(created)
      pollJob(created.id)
    } catch (caught) {
      setPhase('error')
      setErrorKind('download')
      setError(caught instanceof Error ? caught.message : '创建下载任务失败，请稍后重试。')
    }
  }

  const handlePause = async () => {
    if (!job) return
    try {
      const next = await api.pauseJob(job.id)
      setJob(next)
      if (next.status === 'paused') pushToast('已暂停，继续后会从断点续传。', 'info')
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '暂停失败，请稍后重试。', 'error')
    }
  }

  const handleResume = async () => {
    if (!job) return
    try {
      const next = await api.resumeJob(job.id)
      setJob(next)
      pushToast('继续下载，已保留的分片会接着用。', 'info')
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '继续失败，请稍后重试。', 'error')
    }
  }

  const handleCancel = async () => {
    if (!job) return
    if (!window.confirm('取消后，已下载的临时文件会被删除。确定取消吗？')) return
    try {
      const next = await api.cancelJob(job.id)
      setJob(next)
      if (next.status === 'cancelled') {
        stopPolling()
        setPhase('cancelled')
        pushToast('已取消下载，临时文件已清理。', 'info')
      } else {
        pushToast('正在取消，合并阶段会在当前处理完成后清理。', 'info')
      }
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '取消失败，请稍后重试。', 'error')
    }
  }

  const analyze = useCallback(
    async (rawUrl: string) => {
      const extracted = extractVideoUrl(rawUrl)
      const value = (extracted ?? rawUrl).trim()
      if (!value) {
        pushToast('先粘贴一个视频链接。', 'error')
        inputRef.current?.focus()
        return
      }
      if (!isLikelyUrl(value)) {
        pushToast('没有识别到视频链接，直接把分享文字整段粘贴进来也可以。', 'error')
        inputRef.current?.focus()
        return
      }
      if (extracted && extracted !== rawUrl.trim()) {
        setUrl(extracted)
      }

      stopPolling()
      autoDownloaded.current = false
      setPhase('analyzing')
      setResult(null)
      setSelected(null)
      setJob(null)
      setError(null)
      setErrorKind(null)
      setActiveUrl(value)

      try {
        const data = await api.analyze(value)
        setResult(data)
        setSelected(data.formats[0] ?? null)
        setPhase('ready')
        scrollToResult()
      } catch (caught) {
        setPhase('error')
        setErrorKind('analyze')
        setError(caught instanceof Error ? caught.message : '解析失败，请稍后重试。')
      }
    },
    [pushToast, scrollToResult, stopPolling],
  )

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (phase === 'analyzing' || phase === 'downloading') return
    void analyze(url)
  }

  const handlePaste = async () => {
    if (!window.isSecureContext || !navigator.clipboard?.readText) {
      inputRef.current?.focus()
      inputRef.current?.select()
      pushToast('当前是 HTTP 访问，浏览器禁止一键读剪贴板。请长按输入框粘贴，或改用 localhost / HTTPS。', 'info')
      return
    }
    setPasteBusy(true)
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) {
        pushToast('剪贴板里没有内容。', 'info')
        return
      }
      const extracted = extractVideoUrl(text)
      if (!extracted) {
        pushToast('剪贴板里没有识别到视频链接，复制包含链接的整段分享文字也可以。', 'info')
        inputRef.current?.focus()
        return
      }
      setUrl(extracted)
      if (extracted !== text.trim()) {
        pushToast('已从分享文字中提取视频链接。', 'success')
      }
      inputRef.current?.focus()
    } catch {
      inputRef.current?.focus()
      pushToast('没有拿到剪贴板权限。请长按输入框手动粘贴，整段分享文字也可以。', 'info')
    } finally {
      setPasteBusy(false)
    }
  }

  const handleInputPaste = (event: React.ClipboardEvent<HTMLInputElement>) => {
    const text = event.clipboardData.getData('text')
    const extracted = extractVideoUrl(text)
    if (extracted && extracted !== text.trim()) {
      event.preventDefault()
      setUrl(extracted)
      pushToast('已从分享文字中提取视频链接。', 'success')
    }
  }

  const handleSelect = (format: FormatOption) => {
    setSelected(format)
  }

  const handleDownload = () => {
    if (!selected) return
    void startDownload(selected)
  }

  const handleRetry = () => {
    if (errorKind === 'analyze') {
      void analyze(activeUrl || url)
      return
    }
    if (selected) {
      void startDownload(selected)
    }
  }

  const busy = phase === 'analyzing' || phase === 'downloading'

  return (
    <div className="downloader">
      <form className="dock" onSubmit={handleSubmit}>
        <div className="input-row">
          <span className="link-ico" aria-hidden="true">
            <Link2 size={18} />
          </span>
          <label className="sr-only" htmlFor="video-url">
            视频链接
          </label>
          <input
            ref={inputRef}
            id="video-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            onPaste={handleInputPaste}
            placeholder="粘贴视频链接，或整段分享文字"
            autoComplete="off"
            autoCapitalize="none"
            inputMode="url"
            spellCheck={false}
            disabled={busy}
          />
          <button
            className="ghost-btn paste-btn"
            type="button"
            onClick={() => void handlePaste()}
            disabled={busy || pasteBusy}
          >
            {pasteBusy ? '读取中' : '粘贴'}
          </button>
          <button className="go-btn" type="submit" disabled={busy}>
            {phase === 'analyzing' ? (
              <>
                <LoaderCircle className="spin" size={15} />
                识别中
              </>
            ) : (
              <>
                开始收片
                <ChevronRight size={15} strokeWidth={2.4} />
              </>
            )}
          </button>
        </div>
        <div className="dock-foot">
          <span>支持 1,800+ 站点</span>
          <span>无需登录</span>
          <span>下完即删</span>
        </div>
      </form>

      <div className="platforms">
        <span className="platform-label">已支持</span>
        {PLATFORMS.map((platform) => (
          <span className="chip" key={platform.label}>
            <i style={{ background: platform.color }} />
            {platform.label}
          </span>
        ))}
      </div>

      <div className="result-zone" ref={resultRef} aria-live="polite">
        {phase === 'analyzing' && <AnalyzingPanel />}

        {phase === 'error' && !result && (
          <ErrorPanel
            title="这次没解析成功"
            message={error || '请检查链接后重试。'}
            onRetry={handleRetry}
          />
        )}

        {result && phase !== 'analyzing' && (
          <ResultWorkbench
            result={result}
            selected={selected}
            phase={phase}
            job={job}
            error={error}
            onSelect={handleSelect}
            onDownload={handleDownload}
            onPause={handlePause}
            onResume={handleResume}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onSave={() => job && triggerBrowserDownload(job)}
            onClose={reset}
          />
        )}
      </div>
    </div>
  )
}

function AnalyzingPanel() {
  return (
    <div className="analyze-panel">
      <div className="analyze-head">
        <span className="analyze-spinner">
          <LoaderCircle className="spin" size={20} />
        </span>
        <div>
          <strong>正在识别这个链接</strong>
          <span>通常需要 3–15 秒，取决于平台响应速度。</span>
        </div>
      </div>
      <div className="analyze-steps">
        <span className="is-active">
          <Check size={12} /> 识别平台
        </span>
        <span className="is-active">
          <LoaderCircle className="spin" size={12} /> 解析清晰度
        </span>
        <span>准备文件</span>
      </div>
      <div className="analyze-skeleton">
        <div className="skeleton-thumb" />
        <div className="skeleton-lines">
          <i />
          <i />
          <i />
        </div>
      </div>
    </div>
  )
}

function ErrorPanel({
  title,
  message,
  onRetry,
}: {
  title: string
  message: string
  onRetry: () => void
}) {
  return (
    <div className="error-panel">
      <span className="error-icon">
        <AlertTriangle size={20} />
      </span>
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
        <div className="error-actions">
          <button className="small-btn" type="button" onClick={onRetry}>
            <RefreshCw size={14} /> 再试一次
          </button>
          <span>换了链接还是失败？试试公开、非付费、非 DRM 的内容。</span>
        </div>
      </div>
    </div>
  )
}
