import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Download,
  FileText,
  HardDrive,
  Inbox,
  LibraryBig,
  ListChecks,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react'
import { api } from '../lib/api'
import type { LibraryNote } from '../lib/types'
import { MarkdownText } from '../components/MarkdownText'
import { useToast } from '../context/ToastContext'

type StatusFilter = 'all' | 'done' | 'processing' | 'error' | 'trashed'

function stripFrontmatter(source: string): string {
  return source
    .replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '')
    .replace(/^\n+/, '')
}

function formatDate(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatSize(size: number): string {
  if (!size) return '—'
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}

const STATUS_META: Record<string, { label: string; tone: string }> = {
  done: { label: '已完成', tone: 'ok' },
  processing: { label: '整理中', tone: 'working' },
  error: { label: '失败', tone: 'error' },
  trashed: { label: '回收站', tone: 'muted' },
}

export function LibraryPage({ initialNoteId }: { initialNoteId?: string }) {
  const { pushToast } = useToast()
  const [notes, setNotes] = useState<LibraryNote[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [sort, setSort] = useState<'updated' | 'created'>('updated')
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  const [previewNote, setPreviewNote] = useState<LibraryNote | null>(null)
  const [previewContent, setPreviewContent] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const trashMode = status === 'trashed'

  const openedInitial = useRef<string | null>(null)
  const loadSeq = useRef(0)

  const load = useCallback(async () => {
    const seq = ++loadSeq.current
    setLoading(true)
    setError('')
    try {
      const data = await api.listLibrary({
        q: query.trim(),
        status: status === 'all' ? '' : status,
        sort,
        pageSize: 200,
      })
      if (seq !== loadSeq.current) return
      setNotes(data.items)
      setTotal(data.total)
    } catch (caught) {
      if (seq !== loadSeq.current) return
      setError(caught instanceof Error ? caught.message : '笔记仓库加载失败。')
    } finally {
      if (seq === loadSeq.current) setLoading(false)
    }
  }, [query, status, sort])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query ? 260 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  // 生成中的笔记会自动轮询，完成后卡片从“整理中”变为“已完成”。
  useEffect(() => {
    if (!notes.some((note) => note.status === 'processing')) return
    const timer = window.setInterval(() => void load(), 2500)
    return () => window.clearInterval(timer)
  }, [notes, load])

  const openNote = useCallback(
    async (note: LibraryNote) => {
      if (note.status === 'trashed') return
      setPreviewNote(note)
      setPreviewContent('')
      setPreviewError('')
      setPreviewLoading(true)
      try {
        const content = await api.getLibraryContent(note.id)
        setPreviewContent(stripFrontmatter(content))
      } catch (caught) {
        setPreviewError(caught instanceof Error ? caught.message : '笔记内容读取失败。')
      } finally {
        setPreviewLoading(false)
      }
    },
    [],
  )

  useEffect(() => {
    if (!initialNoteId || openedInitial.current === initialNoteId) return
    const note = notes.find((item) => item.id === initialNoteId)
    if (note) {
      openedInitial.current = initialNoteId
      const timer = window.setTimeout(() => void openNote(note), 0)
      return () => window.clearTimeout(timer)
    }
  }, [initialNoteId, notes, openNote])

  const filtered = notes
  const allSelected = filtered.length > 0 && filtered.every((note) => selected.includes(note.id))

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    )
  }

  function enterSelect() {
    setSelectMode(true)
    setSelected([])
  }

  function exitSelect() {
    setSelectMode(false)
    setSelected([])
  }

  async function batchDownload() {
    if (!selected.length || busy) return
    setBusy(true)
    try {
      const blob = await api.downloadLibraryBatch(selected)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'clipdock-notes.zip'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      pushToast(`已打包 ${selected.length} 篇笔记。`, 'success')
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '批量下载失败。', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function batchDelete() {
    if (!selected.length || busy) return
    const count = selected.length
    if (!window.confirm(`把选中的 ${count} 篇笔记移到回收站？之后可以恢复。`)) return
    setBusy(true)
    try {
      const result = await api.batchDeleteLibrary(selected)
      setSelected([])
      if (result.failed.length) {
        pushToast(`已删除 ${result.deleted} 篇，${result.failed.length} 篇失败。`, 'error')
      } else {
        pushToast(`已移入回收站：${result.deleted} 篇。`, 'success')
      }
      if (previewNote && selected.includes(previewNote.id)) {
        setPreviewNote(null)
        setPreviewContent('')
      }
      await load()
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '批量删除失败。', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function batchRestore() {
    if (!selected.length || busy) return
    setBusy(true)
    try {
      const result = await api.batchRestoreLibrary(selected)
      setSelected([])
      if (result.failed.length) {
        pushToast(`已恢复 ${result.restored} 篇，${result.failed.length} 篇失败。`, 'error')
      } else {
        pushToast(`已恢复 ${result.restored} 篇笔记。`, 'success')
      }
      await load()
    } catch (caught) {
      pushToast(caught instanceof Error ? caught.message : '恢复失败。', 'error')
    } finally {
      setBusy(false)
    }
  }

  function downloadOne(note: LibraryNote) {
    window.location.href = `/api/library/${encodeURIComponent(note.id)}/download`
  }

  function closePreview() {
    setPreviewNote(null)
    setPreviewContent('')
    setPreviewError('')
  }

  const platforms = useMemo(
    () => Array.from(new Set(notes.map((note) => note.platform).filter(Boolean))),
    [notes],
  )

  return (
    <div className="library-page">
      <div className="library-head">
        <div>
          <div className="library-kicker">LIBRARY / 笔记仓库</div>
          <h1>收过的视频，都留在这里。</h1>
          <p>每篇都是可带走的 Markdown：AI 摘要、出处、完整文案和原始转写。</p>
        </div>
        <a className="library-back" href="#top">
          <ArrowLeft size={14} /> 回到收片
        </a>
      </div>

      <div className="library-toolbar">
        <div className="library-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            type="search"
            placeholder="搜索标题、AI 摘要、UP 主或出处…"
            aria-label="搜索笔记"
          />
        </div>

        <div className="library-filter-group">
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
            aria-label="按状态筛选"
          >
            <option value="all">全部状态</option>
            <option value="done">已完成</option>
            <option value="processing">整理中</option>
            <option value="error">失败</option>
            <option value="trashed">回收站</option>
          </select>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as 'updated' | 'created')}
            aria-label="排序"
          >
            <option value="updated">最近更新</option>
            <option value="created">最近创建</option>
          </select>
        </div>

        <div className="library-toolbar-right">
          <span className="library-count">{total} 篇</span>
          {!selectMode ? (
            <>
              <button type="button" className="library-small-btn" onClick={enterSelect} disabled={!notes.length}>
                <ListChecks size={14} /> 多选
              </button>
              <button type="button" className="library-small-btn primary" onClick={() => void load()}>
                <RefreshCw size={14} /> 刷新
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="library-small-btn"
                onClick={() =>
                  setSelected(allSelected ? [] : filtered.map((note) => note.id))
                }
              >
                {allSelected ? '取消全选' : `全选（${filtered.length}）`}
              </button>
              <button
                type="button"
                className="library-small-btn"
                onClick={() => setSelected([])}
                disabled={!selected.length}
              >
                清空
              </button>
              {trashMode ? (
                <button
                  type="button"
                  className="library-small-btn primary"
                  onClick={() => void batchRestore()}
                  disabled={!selected.length || busy}
                >
                  <RefreshCw size={14} /> 恢复
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="library-small-btn"
                    onClick={() => void batchDownload()}
                    disabled={!selected.length || busy}
                  >
                    <Download size={14} /> 下载 zip
                  </button>
                  <button
                    type="button"
                    className="library-small-btn danger"
                    onClick={() => void batchDelete()}
                    disabled={!selected.length || busy}
                  >
                    <Trash2 size={14} /> 删除
                  </button>
                </>
              )}
              <button type="button" className="library-small-btn" onClick={exitSelect}>
                退出多选
              </button>
            </>
          )}
        </div>
      </div>

      {platforms.length > 1 ? (
        <div className="library-platform-row">
          <span>平台</span>
          {platforms.map((platform) => (
            <button key={platform} type="button" onClick={() => setQuery(platform)}>
              {platform}
            </button>
          ))}
        </div>
      ) : null}

      {error ? (
        <div className="library-error">
          <AlertTriangle size={16} />
          <span>{error}</span>
          <button type="button" onClick={() => void load()}>
            重试
          </button>
        </div>
      ) : null}

      {loading && !notes.length ? (
        <div className="library-loading">
          <Loader2 className="spin" size={18} />
          <span>读取笔记…</span>
        </div>
      ) : null}

      {!loading && !notes.length && !error ? (
        <div className="library-empty">
          <div className="library-empty-icon">
            <LibraryBig size={26} />
          </div>
          <h2>
            {trashMode
              ? '回收站是空的'
              : query || status !== 'all'
                ? '没有匹配的笔记'
                : '仓库还空着'}
          </h2>
          <p>
            {trashMode
              ? '删除的笔记会在这里保留 7 天，可以恢复。'
              : query || status !== 'all'
                ? '换个关键词或状态筛选试试。'
                : '去收片页解析一个视频，点「AI 视频总结」，就会自动生成第一篇 Markdown。'}
          </p>
          <a className="library-small-btn primary" href="#top">
            <Inbox size={14} /> 去收片
          </a>
        </div>
      ) : null}

      {notes.length ? (
        <div className="library-grid">
          {notes.map((note) => {
            const meta = STATUS_META[note.status] ?? STATUS_META.done
            const checked = selected.includes(note.id)
            return (
              <article
                key={note.id}
                className={`library-card ${checked ? 'is-selected' : ''} ${selectMode ? 'is-selectable' : ''}`}
                onClick={() => {
                  if (trashMode) {
                    setSelectMode(true)
                    toggle(note.id)
                  } else if (selectMode) {
                    toggle(note.id)
                  } else {
                    void openNote(note)
                  }
                }}
              >
                <div className="library-card-top">
                  <span className={`library-status ${meta.tone}`}>
                    <i />
                    {meta.label}
                  </span>
                  <span className="library-card-date">{formatDate(note.updatedAt)}</span>
                  {selectMode ? (
                    <span className={`library-check ${checked ? 'checked' : ''}`}>
                      {checked ? <Check size={12} /> : null}
                    </span>
                  ) : null}
                </div>

                <h2>{note.title || '未命名视频'}</h2>
                <p className="library-summary">{note.aiSummary || '摘要生成中…'}</p>

                <div className="library-source">
                  {note.platform ? <span className="library-platform">{note.platform}</span> : null}
                  {note.uploader ? <span>{note.uploader}</span> : null}
                  {note.durationText ? <span>{note.durationText}</span> : null}
                </div>

                <div className="library-card-foot">
                  <span>
                    <FileText size={12} /> {note.fileName || 'Markdown'}
                  </span>
                  <span>
                    <HardDrive size={12} /> {formatSize(note.fileSize)}
                  </span>
                </div>
              </article>
            )
          })}
        </div>
      ) : null}

      {previewNote ? (
        <div className="library-overlay" role="dialog" aria-modal="true" aria-label="笔记预览">
          <div className="library-preview">
            <header className="library-preview-head">
              <div>
                <span className="library-kicker">PREVIEW / 笔记预览</span>
                <h2>{previewNote.title || '未命名视频'}</h2>
                <div className="library-preview-meta">
                  {previewNote.platform ? <span>{previewNote.platform}</span> : null}
                  {previewNote.uploader ? <span>{previewNote.uploader}</span> : null}
                  {previewNote.durationText ? <span>{previewNote.durationText}</span> : null}
                  <span>{formatDate(previewNote.updatedAt)}</span>
                </div>
              </div>
              <button type="button" className="library-close" onClick={closePreview} aria-label="关闭预览">
                <X size={18} />
              </button>
            </header>

            {previewNote.status === 'processing' ? (
              <div className="library-preview-banner">
                <Loader2 className="spin" size={14} /> 这篇笔记还在生成，下面是可以预览的草稿内容。
              </div>
            ) : null}
            {previewNote.status === 'error' ? (
              <div className="library-preview-banner error">
                <AlertTriangle size={14} /> {previewNote.error || '这篇笔记生成失败，可以重新生成。'}
              </div>
            ) : null}

            <div className="library-preview-content">
              {previewLoading ? (
                <div className="library-loading">
                  <Loader2 className="spin" size={16} />
                  <span>读取 Markdown…</span>
                </div>
              ) : previewError ? (
                <div className="library-error">
                  <AlertTriangle size={15} />
                  <span>{previewError}</span>
                  <button type="button" onClick={() => void openNote(previewNote)}>
                    重试
                  </button>
                </div>
              ) : (
                <MarkdownText source={previewContent} className="article-body" />
              )}
            </div>

            <footer className="library-preview-actions">
              <button type="button" className="library-small-btn primary" onClick={() => downloadOne(previewNote)}>
                <Download size={14} /> 下载 .md
              </button>
              {previewNote.sourceUrl ? (
                <a
                  className="library-small-btn"
                  href={previewNote.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  查看原视频
                </a>
              ) : null}
              <span className="library-preview-file">{previewNote.fileName}</span>
              <button type="button" className="library-small-btn" onClick={closePreview}>
                关闭
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  )
}
