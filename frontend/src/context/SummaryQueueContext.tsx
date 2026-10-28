import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { api } from '../lib/api'
import { extractVideoUrls } from '../lib/format'
import { isTaskActive } from '../lib/summary'
import type { AnalyzeResult, SummaryJob, SummaryTask } from '../lib/types'
import { useToast } from './ToastContext'

export type SummaryPayload = Pick<
  AnalyzeResult,
  'title' | 'thumbnail' | 'platform' | 'uploader' | 'duration' | 'webpageUrl'
>

export interface BatchEnqueueResult {
  queued: number
  failed: number
  skipped: number
  ignored: number
  total: number
}

interface SummaryQueueContextValue {
  tasks: SummaryTask[]
  activeCount: number
  notificationsEnabled: boolean
  enqueueOne: (payload: SummaryPayload) => Promise<SummaryTask>
  enqueueUrls: (text: string) => Promise<BatchEnqueueResult>
  cancelTask: (id: string) => Promise<void>
  retryTask: (id: string) => Promise<SummaryTask>
  dismissTask: (id: string) => void
  loadTask: (id: string) => Promise<SummaryTask>
  getTask: (id: string) => SummaryTask | undefined
  findByUrl: (url: string) => SummaryTask | undefined
  refresh: () => Promise<void>
  toggleNotifications: () => Promise<void>
}

const STORAGE_KEY = 'clipdock.summary.tasks.v1'
const NOTIFY_KEY = 'clipdock.summary.notify.v1'
const MAX_TASKS = 30
const BATCH_LIMIT = 12
const ANALYZE_CONCURRENCY = 3
const POLL_INTERVAL = 1200
const MAX_BACKOFF = 5000

function nowSeconds(): number {
  return Math.floor(Date.now() / 1000)
}

function newLocalId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `local_${crypto.randomUUID()}`
  }
  return `local_${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function isLocalTask(task: SummaryTask): boolean {
  return task.id.startsWith('local_')
}

function taskFromJob(job: SummaryJob, fallbackUrl = ''): SummaryTask {
  return {
    ...job,
    url: job.url || fallbackUrl,
    addedAt: job.createdAt,
  }
}

function localTask(url: string): SummaryTask {
  const stamp = nowSeconds()
  return {
    id: newLocalId(),
    url,
    status: 'analyzing',
    stage: 'analyzing',
    progress: 0,
    title: url,
    thumbnail: null,
    platform: null,
    uploader: null,
    duration: 0,
    transcriptSource: null,
    transcriptAvailable: false,
    transcriptChars: 0,
    result: null,
    articleStatus: 'idle',
    articleProgress: 0,
    articleChars: 0,
    articleError: null,
    noteId: null,
    error: null,
    errorCode: null,
    canCancel: true,
    canRetry: false,
    createdAt: stamp,
    updatedAt: stamp,
    addedAt: stamp,
  }
}

function upsertTask(tasks: SummaryTask[], task: SummaryTask): SummaryTask[] {
  const index = tasks.findIndex((item) => item.id === task.id)
  if (index === -1) {
    return [task, ...tasks].slice(0, MAX_TASKS)
  }
  const next = [...tasks]
  next[index] = {
    ...tasks[index],
    ...task,
    addedAt: tasks[index].addedAt ?? task.addedAt,
  }
  return next
}

function mergeServerItems(
  tasks: SummaryTask[],
  items: SummaryJob[],
): SummaryTask[] {
  if (!items.length) return tasks
  const byId = new Map(items.map((item) => [item.id, item]))
  return tasks.map((task) => {
    if (isLocalTask(task)) return task
    const server = byId.get(task.id)
    if (!server) return task
    const merged: SummaryTask = {
      ...task,
      ...server,
      url: server.url || task.url,
      addedAt: task.addedAt ?? server.createdAt,
      result: server.result ?? task.result,
    }
    return merged
  })
}

function readInitialTasks(): SummaryTask[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const data = JSON.parse(raw) as { version?: number; tasks?: unknown }
    if (!Array.isArray(data.tasks)) return []
    return data.tasks
      .filter(
        (item): item is SummaryTask =>
          typeof item === 'object' &&
          item !== null &&
          typeof (item as SummaryTask).id === 'string' &&
          typeof (item as SummaryTask).url === 'string',
      )
      .slice(0, MAX_TASKS)
      .map((task) =>
        task.status === 'analyzing'
          ? {
              ...task,
              status: 'error' as const,
              stage: 'error',
              error: '页面刷新，解析已中断，请重试。',
              errorCode: 'ANALYZE_INTERRUPTED',
              canRetry: true,
            }
          : task,
      )
  } catch {
    return []
  }
}

function persistTasks(tasks: SummaryTask[]): void {
  try {
    const serializable = tasks.slice(0, MAX_TASKS).map((task) => {
      const copy: Record<string, unknown> = { ...task }
      delete copy.result
      return copy
    })
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: 1, tasks: serializable }),
    )
  } catch {
    // Local storage can be full or disabled; the server remains authoritative.
  }
}

function readNotifyPreference(): boolean {
  try {
    return window.localStorage.getItem(NOTIFY_KEY) === '1'
  } catch {
    return false
  }
}

async function runPool<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  let index = 0
  const runners = Array.from(
    { length: Math.min(limit, items.length) },
    async () => {
      while (index < items.length) {
        const item = items[index]
        index += 1
        await worker(item)
      }
    },
  )
  await Promise.all(runners)
}

const SummaryQueueContext = createContext<SummaryQueueContextValue | null>(null)

export function SummaryQueueProvider({ children }: { children: ReactNode }) {
  const { pushToast } = useToast()
  const [tasks, setTasks] = useState<SummaryTask[]>(readInitialTasks)
  const [notificationsEnabled, setNotificationsEnabled] = useState(
    readNotifyPreference,
  )
  const tasksRef = useRef(tasks)
  const pollingRef = useRef(false)
  const cancelledLocalIds = useRef<Set<string>>(new Set())
  const loadingIds = useRef<Set<string>>(new Set())
  const baseTitle = useRef(document.title)

  useEffect(() => {
    tasksRef.current = tasks
    persistTasks(tasks)
  }, [tasks])

  // These two read React state, not the polling ref: a child must see the
  // newly merged task in the same render that follows setTasks.
  const getTask = useCallback(
    (id: string) => tasks.find((task) => task.id === id),
    [tasks],
  )

  const findByUrl = useCallback(
    (url: string) => tasks.find((task) => task.url === url),
    [tasks],
  )

  const notify = useCallback(
    (title: string, body: string, tone: 'success' | 'error' | 'info') => {
      pushToast(`${title} ${body}`.trim(), tone)
      if (
        notificationsEnabled &&
        document.hidden &&
        typeof Notification !== 'undefined' &&
        Notification.permission === 'granted'
      ) {
        try {
          new Notification(title, { body })
        } catch {
          // Notifications can be blocked by the browser even when granted.
        }
      }
    },
    [notificationsEnabled, pushToast],
  )

  // Merge server state once on mount so a page refresh reattaches to jobs.
  useEffect(() => {
    const ids = tasksRef.current
      .filter((task) => !isLocalTask(task))
      .map((task) => task.id)
    if (!ids.length) return
    let cancelled = false
    void api
      .listSummaries({ ids, limit: 50 })
      .then((data) => {
        if (cancelled) return
        const returned = new Set(data.items.map((item) => item.id))
        setTasks((current) =>
          mergeServerItems(current, data.items).map((task) =>
            !isLocalTask(task) &&
            !returned.has(task.id) &&
            task.status !== 'error'
              ? {
                  ...task,
                  status: 'error',
                  stage: 'error',
                  error: '任务不存在或已过期，可以重新创建。',
                  errorCode: 'SUMMARY_NOT_FOUND',
                  canRetry: true,
                  updatedAt: nowSeconds(),
                }
              : task,
          ),
        )
      })
      .catch(() => {
        // Keep local state; the next poll or manual refresh can recover.
      })
    return () => {
      cancelled = true
    }
  }, [])

  const hasActive = tasks.some(isTaskActive)
  const activeCount = useMemo(
    () => tasks.filter((task) => isTaskActive(task)).length,
    [tasks],
  )

  useEffect(() => {
    if (!hasActive) return
    let cancelled = false
    let timer: number | undefined
    let backoff = POLL_INTERVAL

    const tick = async () => {
      if (cancelled) return
      const ids = tasksRef.current
        .filter((task) => !isLocalTask(task) && isTaskActive(task))
        .map((task) => task.id)
      if (!ids.length) {
        timer = window.setTimeout(tick, POLL_INTERVAL)
        return
      }
      if (pollingRef.current) {
        timer = window.setTimeout(tick, 400)
        return
      }
      pollingRef.current = true
      try {
        const data = await api.listSummaries({ ids, limit: 50 })
        if (cancelled) return
        const previous = new Map(tasksRef.current.map((task) => [task.id, task]))
        data.items.forEach((item) => {
          const before = previous.get(item.id)
          if (!before) return
          if (before.status !== item.status) {
            if (item.status === 'done') {
              notify(`《${item.title}》总结完成`, '打开任务中心查看结果。', 'success')
            } else if (item.status === 'error') {
              notify(
                `《${item.title}》总结失败`,
                item.error || '可以打开任务中心重试。',
                'error',
              )
            } else if (item.status === 'cancelled') {
              notify(`《${item.title}》已取消`, '可以在任务中心重新开始。', 'info')
            }
          }
        })
        const returned = new Set(data.items.map((item) => item.id))
        setTasks((current) =>
          mergeServerItems(current, data.items).map((task) =>
            !isLocalTask(task) &&
            !returned.has(task.id) &&
            isTaskActive(task)
              ? {
                  ...task,
                  status: 'error',
                  stage: 'error',
                  error: '任务不存在或已过期，可以重新创建。',
                  errorCode: 'SUMMARY_NOT_FOUND',
                  canRetry: true,
                  updatedAt: nowSeconds(),
                }
              : task,
          ),
        )
        backoff = POLL_INTERVAL
      } catch {
        backoff = Math.min(MAX_BACKOFF, Math.round(backoff * 1.7))
      } finally {
        pollingRef.current = false
        if (!cancelled) {
          timer = window.setTimeout(
            tick,
            document.hidden ? 5000 : backoff,
          )
        }
      }
    }

    timer = window.setTimeout(tick, 0)
    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [hasActive, notify])

  useEffect(() => {
    document.title =
      activeCount > 0
        ? `(${activeCount}) ${baseTitle.current}`
        : baseTitle.current
    return () => {
      document.title = baseTitle.current
    }
  }, [activeCount])

  const enqueueOne = useCallback(
    async (payload: SummaryPayload) => {
      const existing = tasksRef.current.find(
        (task) => task.url === payload.webpageUrl,
      )
      if (existing) return existing
      const job = await api.createSummary(payload)
      const task = taskFromJob(job, payload.webpageUrl)
      setTasks((current) => upsertTask(current, task))
      return task
    },
    [],
  )

  const retryTask = useCallback(async (id: string) => {
    const task = tasksRef.current.find((item) => item.id === id)
    if (!task) throw new Error('任务不存在。')
    cancelledLocalIds.current.delete(id)
    if (isLocalTask(task)) {
      try {
        const meta = await api.analyze(task.url)
        const job = await api.createSummary(meta)
        const next = taskFromJob(job, meta.webpageUrl || task.url)
        setTasks((current) =>
          upsertTask(
            current.filter((item) => item.id !== task.id),
            next,
          ),
        )
        return next
      } catch (caught) {
        const message =
          caught instanceof Error ? caught.message : '重新解析失败，请稍后重试。'
        setTasks((current) =>
          current.map((item) =>
            item.id === task.id
              ? {
                  ...item,
                  status: 'error',
                  stage: 'error',
                  error: message,
                  localError: message,
                  canRetry: true,
                  updatedAt: nowSeconds(),
                }
              : item,
          ),
        )
        throw caught
      }
    }
    const job = await api.retrySummary(id)
    const next = taskFromJob(job, task.url)
    setTasks((current) => upsertTask(current, next))
    return next
  }, [])

  const cancelTask = useCallback(async (id: string) => {
    const task = tasksRef.current.find((item) => item.id === id)
    if (!task) return
    if (isLocalTask(task)) {
      cancelledLocalIds.current.add(id)
      setTasks((current) => current.filter((item) => item.id !== id))
      return
    }
    const job = await api.cancelSummary(id)
    const next = taskFromJob(job, task.url)
    setTasks((current) => upsertTask(current, next))
  }, [])

  const dismissTask = useCallback((id: string) => {
    setTasks((current) => current.filter((task) => task.id !== id))
  }, [])

  const loadTask = useCallback(async (id: string) => {
    if (loadingIds.current.has(id)) {
      const existing = tasksRef.current.find((task) => task.id === id)
      if (existing) return existing
    }
    loadingIds.current.add(id)
    try {
      const job = await api.getSummary(id)
      const task = taskFromJob(job)
      setTasks((current) => upsertTask(current, task))
      return task
    } finally {
      loadingIds.current.delete(id)
    }
  }, [])

  const refresh = useCallback(async () => {
    const ids = tasksRef.current
      .filter((task) => !isLocalTask(task))
      .map((task) => task.id)
    if (!ids.length) return
    const data = await api.listSummaries({ ids, limit: 50 })
    setTasks((current) => mergeServerItems(current, data.items))
  }, [])

  const enqueueUrls = useCallback(async (text: string) => {
    const all = extractVideoUrls(text)
    if (!all.length) {
      throw new Error('没有识别到视频链接，请检查后重试。')
    }
    const limited = all.slice(0, BATCH_LIMIT)
    const ignored = Math.max(0, all.length - limited.length)
    const existingUrls = new Set(
      tasksRef.current.filter((task) => !isLocalTask(task)).map((task) => task.url),
    )
    const urls = limited.filter((url) => !existingUrls.has(url))
    const skipped = limited.length - urls.length
    if (!urls.length) {
      return {
        queued: 0,
        failed: 0,
        skipped,
        ignored,
        total: limited.length,
      }
    }

    const locals = urls.map(localTask)
    setTasks((current) => [...locals, ...current].slice(0, MAX_TASKS))

    let queued = 0
    let failed = 0
    await runPool(locals, ANALYZE_CONCURRENCY, async (local) => {
      if (cancelledLocalIds.current.has(local.id)) {
        cancelledLocalIds.current.delete(local.id)
        return
      }
      try {
        const meta = await api.analyze(local.url)
        if (cancelledLocalIds.current.has(local.id)) {
          cancelledLocalIds.current.delete(local.id)
          return
        }
        const job = await api.createSummary(meta)
        if (cancelledLocalIds.current.has(local.id)) {
          cancelledLocalIds.current.delete(local.id)
          return
        }
        const task = taskFromJob(job, meta.webpageUrl || local.url)
        setTasks((current) =>
          upsertTask(
            current.filter((item) => item.id !== local.id),
            task,
          ),
        )
        queued += 1
      } catch (caught) {
        if (cancelledLocalIds.current.has(local.id)) {
          cancelledLocalIds.current.delete(local.id)
          return
        }
        failed += 1
        const message =
          caught instanceof Error ? caught.message : '解析失败，请稍后重试。'
        setTasks((current) =>
          current.map((item) =>
            item.id === local.id
              ? {
                  ...item,
                  status: 'error',
                  stage: 'error',
                  error: message,
                  localError: message,
                  canRetry: true,
                  updatedAt: nowSeconds(),
                }
              : item,
          ),
        )
      }
    })

    return {
      queued,
      failed,
      skipped,
      ignored,
      total: limited.length,
    }
  }, [])

  const toggleNotifications = useCallback(async () => {
    if (notificationsEnabled) {
      setNotificationsEnabled(false)
      try {
        window.localStorage.setItem(NOTIFY_KEY, '0')
      } catch {
        // Ignore storage errors.
      }
      return
    }
    if (typeof Notification === 'undefined') {
      pushToast('当前浏览器不支持桌面通知，完成时仍会显示页面提示。', 'info')
      return
    }
    if (Notification.permission === 'denied') {
      pushToast('桌面通知已被浏览器拒绝，请在站点设置里重新允许。', 'info')
      return
    }
    const permission =
      Notification.permission === 'granted'
        ? 'granted'
        : await Notification.requestPermission()
    if (permission !== 'granted') {
      pushToast('没有获得桌面通知权限，完成时仍会显示页面提示。', 'info')
      return
    }
    setNotificationsEnabled(true)
    try {
      window.localStorage.setItem(NOTIFY_KEY, '1')
    } catch {
      // Ignore storage errors.
    }
  }, [notificationsEnabled, pushToast])

  const value = useMemo(
    () => ({
      tasks,
      activeCount,
      notificationsEnabled,
      enqueueOne,
      enqueueUrls,
      cancelTask,
      retryTask,
      dismissTask,
      loadTask,
      getTask,
      findByUrl,
      refresh,
      toggleNotifications,
    }),
    [
      tasks,
      activeCount,
      notificationsEnabled,
      enqueueOne,
      enqueueUrls,
      cancelTask,
      retryTask,
      dismissTask,
      loadTask,
      getTask,
      findByUrl,
      refresh,
      toggleNotifications,
    ],
  )

  return (
    <SummaryQueueContext.Provider value={value}>
      {children}
    </SummaryQueueContext.Provider>
  )
}

export function useSummaryQueue(): SummaryQueueContextValue {
  const context = useContext(SummaryQueueContext)
  if (!context) {
    throw new Error('useSummaryQueue must be used inside SummaryQueueProvider')
  }
  return context
}
