import { useState } from 'react'
import {
  AlertTriangle,
  ArrowDownToLine,
  Check,
  Clock3,
  Download,
  Info,
  LoaderCircle,
  Music2,
  Pause,
  Play,
  RefreshCw,
  ShieldCheck,
  Smartphone,
  X,
  XCircle,
} from 'lucide-react'
import { jobStatusLabel } from '../lib/api'
import { formatBytes, heightLabel } from '../lib/format'
import type { AnalyzeResult, FormatOption, Job, LoadPhase } from '../lib/types'
import { SummaryPanel } from './SummaryPanel'

export function ResultWorkbench({
  result,
  selected,
  phase,
  job,
  error,
  onSelect,
  onDownload,
  onPause,
  onResume,
  onCancel,
  onRetry,
  onSave,
  onClose,
}: {
  result: AnalyzeResult
  selected: FormatOption | null
  phase: LoadPhase
  job: Job | null
  error: string | null
  onSelect: (format: FormatOption) => void
  onDownload: () => void
  onPause: () => void
  onResume: () => void
  onCancel: () => void
  onRetry: () => void
  onSave: () => void
  onClose: () => void
}) {
  const isWorking = phase === 'downloading'
  const isDone = phase === 'done'
  const isCancelled = phase === 'cancelled'

  return (
    <div className="workbench">
      <section className="workbench-main">
        <div className="reader-head">
          <div className="reader-kicker">READING / 视频资料</div>
          <h2>{result.title}</h2>
          <div className="reader-meta">
            <span>{result.platform}</span>
            <span>·</span>
            <span>{result.uploader}</span>
            <span>·</span>
            <span>{result.durationText}</span>
            {result.sourceHeight ? (
              <>
                <span>·</span>
                <span>当前最高 {heightLabel(result.sourceHeight)}</span>
              </>
            ) : null}
          </div>
        </div>
        <SummaryPanel key={result.webpageUrl} result={result} variant="reader" />
      </section>

      <aside className="workbench-rail">
        <article className="rail-card">
          <div className="rail-head">
            <div>
              <span className="result-kicker">MEDIA / 收片</span>
              <span className="result-platform">{result.platform}</span>
            </div>
            <button className="icon-btn" type="button" onClick={onClose} aria-label="关闭结果">
              <X size={17} />
            </button>
          </div>

          <RailCover result={result} />

          <div className="rail-info">
            <h3>{result.title}</h3>
            <p>
              {result.uploader}
              <span>·</span>
              {result.durationText}
            </p>
          </div>

          <div className="rail-trust">
            <span>
              <ShieldCheck size={12} /> 临时中转
            </span>
            <span>
              <Smartphone size={12} /> 手机可存
            </span>
            <span>
              <Clock3 size={12} /> 30 分钟清理
            </span>
          </div>

          <div className="format-section rail-formats-section">
            <div className="format-head">
              <span>选择画质</span>
              <span className="format-hint">源站实际可用</span>
            </div>
            <div className="rail-formats">
              {result.formats.map((format) => {
                const active = selected?.id === format.id
                return (
                  <button
                    key={format.id}
                    type="button"
                    className={`format-option ${active ? 'is-selected' : ''}`}
                    aria-pressed={active}
                    onClick={() => onSelect(format)}
                    disabled={isWorking}
                  >
                    <span className="format-top">
                      <strong>{format.label}</strong>
                      {format.kind === 'audio' ? <Music2 size={13} /> : null}
                    </span>
                    <span className="format-sub">{format.sublabel}</span>
                    <span className="format-size">{format.sizeText || '大小以实际为准'}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {result.qualityNotice ? (
            <div className="quality-notice" role="note">
              <span className="quality-notice-icon">
                <Info size={14} />
              </span>
              <div>
                <strong>为什么没有更高画质？</strong>
                <span>{result.qualityNotice.message}</span>
              </div>
            </div>
          ) : null}

          {isWorking && job && (
            <RailProgress
              job={job}
              onPause={onPause}
              onResume={onResume}
              onCancel={onCancel}
            />
          )}

          {isDone && job && (
            <div className="success-panel rail-success">
              <div className="success-icon">
                <Check size={18} strokeWidth={2.6} />
              </div>
              <div className="success-copy">
                <strong>收好了，文件已开始下载。</strong>
                <span>
                  {job.filename || '视频文件'}
                  {job.filesize ? ` · ${formatBytes(job.filesize)}` : ''}
                </span>
              </div>
              <button className="small-btn" type="button" onClick={onSave}>
                <Download size={13} /> 再保存
              </button>
            </div>
          )}

          {phase === 'error' && (
            <div className="inline-error rail-error">
              <AlertTriangle size={14} />
              <span>{error || '下载失败，请重试。'}</span>
              <button type="button" onClick={onRetry}>
                重试 <RefreshCw size={12} />
              </button>
            </div>
          )}

          {isCancelled && (
            <div className="cancelled-panel rail-cancelled">
              <XCircle size={14} />
              <span>已取消，临时文件已清理。可以重新下载。</span>
            </div>
          )}

          <div className="result-action rail-action">
            <div className="result-action-note">
              <span className="mini-tag">{selected?.kind === 'audio' ? 'MP3' : 'MP4'}</span>
              <span>{selected?.kind === 'audio' ? '192kbps' : '自动合并音视频'}</span>
            </div>
            <button
              className="download-btn"
              type="button"
              onClick={onDownload}
              disabled={isWorking || !selected}
            >
              {isWorking ? (
                <>
                  <LoaderCircle className="spin" size={15} />
                  正在收片…
                </>
              ) : isCancelled ? (
                <>
                  <Download size={15} />
                  重新下载
                </>
              ) : isDone ? (
                <>
                  <Download size={15} />
                  再下一次
                </>
              ) : (
                <>
                  <ArrowDownToLine size={16} />
                  下载 {selected?.label ?? ''}
                </>
              )}
            </button>
          </div>
        </article>
      </aside>
    </div>
  )
}

function RailCover({ result }: { result: AnalyzeResult }) {
  const [failedThumbnail, setFailedThumbnail] = useState<string | null>(null)
  const thumbFailed = Boolean(result.thumbnail) && failedThumbnail === result.thumbnail
  return (
    <div className={`rail-cover ${thumbFailed ? 'thumb-fallback' : ''}`}>
      {result.thumbnail && !thumbFailed ? (
        <img
          src={result.thumbnail}
          alt=""
          referrerPolicy="no-referrer"
          loading="lazy"
          onError={() => setFailedThumbnail(result.thumbnail)}
        />
      ) : (
        <span className="thumb-placeholder">
          <Play size={22} fill="currentColor" strokeWidth={0} />
        </span>
      )}
      <span className="thumb-duration">{result.durationText}</span>
      <span className="thumb-source">{result.platform}</span>
    </div>
  )
}

function RailProgress({
  job,
  onPause,
  onResume,
  onCancel,
}: {
  job: Job
  onPause: () => void
  onResume: () => void
  onCancel: () => void
}) {
  const percent = Math.round(job.progress)
  return (
    <div className="progress-panel rail-progress">
      <div className="progress-head">
        <div>
          <span className="progress-status">
            {job.status === 'processing' ||
            job.status === 'pausing' ||
            job.status === 'cancelling' ? (
              <LoaderCircle className="spin" size={13} />
            ) : job.status === 'paused' ? (
              <Pause size={13} />
            ) : (
              <ArrowDownToLine size={13} />
            )}
            {jobStatusLabel(job.status)}
          </span>
          <span className="progress-sub">
            {job.status === 'processing'
              ? '音视频合并中，马上就好'
              : job.status === 'paused'
                ? '已暂停，继续后断点续传'
                : job.status === 'cancelling'
                  ? '正在清理临时文件'
                  : '完成后自动保存到本地'}
          </span>
        </div>
        <strong>{percent}%</strong>
      </div>
      <div
        className="progress-bar"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i style={{ width: `${Math.max(percent, 2)}%` }} />
      </div>
      <div className="progress-stats">
        <span>{job.status === 'paused' ? '已保留分片' : job.speed || '连接中…'}</span>
        <span>
          {job.status === 'paused'
            ? '点击继续'
            : job.eta
              ? `剩余 ${job.eta}`
              : '计算剩余时间…'}
        </span>
        <span>
          {formatBytes(job.downloadedBytes)}
          {job.totalBytes ? ` / ${formatBytes(job.totalBytes)}` : ''}
        </span>
      </div>
      <div className="job-controls">
        {job.canPause ? (
          <button type="button" className="job-control-btn" onClick={onPause}>
            <Pause size={13} /> 暂停
          </button>
        ) : null}
        {job.canResume ? (
          <button type="button" className="job-control-btn primary" onClick={onResume}>
            <Play size={13} /> 继续
          </button>
        ) : null}
        {job.canCancel ? (
          <button type="button" className="job-control-btn danger" onClick={onCancel}>
            <XCircle size={13} /> 取消
          </button>
        ) : null}
      </div>
    </div>
  )
}
