import type {
  AnalyzeResult,
  ArticlePayload,
  Health,
  Job,
  JobStatus,
  LibraryList,
  SummaryJob,
  SummaryListResponse,
  TranscriptPayload,
} from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  code: string

  constructor(message: string, status = 0, code = 'REQUEST_FAILED') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError('无法连接服务器，请确认服务已启动。', 0, 'NETWORK_ERROR')
  }

  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    let code = 'REQUEST_FAILED'
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } }
      message = body.error?.message || message
      code = body.error?.code || code
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new ApiError(message, response.status, code)
  }

  return (await response.json()) as T
}

async function requestRaw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch {
    throw new ApiError('无法连接服务器，请确认服务已启动。', 0, 'NETWORK_ERROR')
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    let code = 'REQUEST_FAILED'
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } }
      message = body.error?.message || message
      code = body.error?.code || code
    } catch {
      // Keep the generic message when the body is not JSON.
    }
    throw new ApiError(message, response.status, code)
  }
  return response
}

export const api = {
  analyze(url: string) {
    return request<AnalyzeResult>('/api/analyze', {
      method: 'POST',
      body: JSON.stringify({ url }),
    })
  },

  createJob(
    url: string,
    format: string,
    meta: Pick<AnalyzeResult, 'title' | 'thumbnail' | 'platform'>,
  ) {
    return request<Job>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({
        url,
        format,
        meta: {
          title: meta.title,
          thumbnail: meta.thumbnail,
          platform: meta.platform,
        },
      }),
    })
  },

  getJob(id: string) {
    return request<Job>(`/api/jobs/${encodeURIComponent(id)}`)
  },

  pauseJob(id: string) {
    return request<Job>(`/api/jobs/${encodeURIComponent(id)}/pause`, { method: 'POST' })
  },

  resumeJob(id: string) {
    return request<Job>(`/api/jobs/${encodeURIComponent(id)}/resume`, { method: 'POST' })
  },

  cancelJob(id: string) {
    return request<Job>(`/api/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' })
  },

  createSummary(
    payload: Pick<
      AnalyzeResult,
      'title' | 'thumbnail' | 'platform' | 'uploader' | 'duration' | 'webpageUrl'
    >,
  ) {
    return request<SummaryJob>('/api/summaries', {
      method: 'POST',
      body: JSON.stringify({
        url: payload.webpageUrl,
        title: payload.title,
        thumbnail: payload.thumbnail,
        platform: payload.platform,
        uploader: payload.uploader,
        duration: payload.duration,
      }),
    })
  },

  getSummary(id: string) {
    return request<SummaryJob>(`/api/summaries/${encodeURIComponent(id)}`)
  },

  listSummaries(
    params: { ids?: string[]; status?: string; limit?: number } = {},
  ) {
    const search = new URLSearchParams()
    if (params.ids?.length) search.set('ids', params.ids.join(','))
    if (params.status) search.set('status', params.status)
    if (params.limit) search.set('limit', String(params.limit))
    const query = search.toString()
    return request<SummaryListResponse>(`/api/summaries${query ? `?${query}` : ''}`)
  },

  cancelSummary(id: string) {
    return request<SummaryJob>(`/api/summaries/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
    })
  },

  retrySummary(id: string) {
    return request<SummaryJob>(`/api/summaries/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
    })
  },

  getTranscript(id: string) {
    return request<TranscriptPayload>(`/api/summaries/${encodeURIComponent(id)}/transcript`)
  },

  getArticle(id: string) {
    return request<ArticlePayload>(`/api/summaries/${encodeURIComponent(id)}/article`)
  },

  createArticle(id: string) {
    return request<SummaryJob>(`/api/summaries/${encodeURIComponent(id)}/article`, {
      method: 'POST',
    })
  },

  listLibrary(params: {
    q?: string
    status?: string
    platform?: string
    sort?: string
    page?: number
    pageSize?: number
  } = {}) {
    const search = new URLSearchParams()
    if (params.q) search.set('q', params.q)
    if (params.status) search.set('status', params.status)
    if (params.platform) search.set('platform', params.platform)
    if (params.sort) search.set('sort', params.sort)
    if (params.page) search.set('page', String(params.page))
    if (params.pageSize) search.set('page_size', String(params.pageSize))
    const query = search.toString()
    return request<LibraryList>(`/api/library${query ? `?${query}` : ''}`)
  },

  async getLibraryContent(id: string) {
    const response = await requestRaw(`/api/library/${encodeURIComponent(id)}/content`)
    return response.text()
  },

  async downloadLibraryBatch(ids: string[]) {
    const response = await requestRaw('/api/library/batch-download', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    })
    return response.blob()
  },

  batchDeleteLibrary(ids: string[]) {
    return request<{ deleted: number; failed: string[] }>('/api/library/batch-delete', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    })
  },

  batchRestoreLibrary(ids: string[]) {
    return request<{ restored: number; failed: string[] }>('/api/library/batch-restore', {
      method: 'POST',
      body: JSON.stringify({ ids }),
    })
  },

  health() {
    return request<Health>('/api/health')
  },
}

export function jobStatusLabel(status: JobStatus): string {
  switch (status) {
    case 'queued':
      return '排队中'
    case 'downloading':
      return '正在收片'
    case 'pausing':
      return '正在暂停'
    case 'paused':
      return '已暂停'
    case 'processing':
      return '正在合并'
    case 'cancelling':
      return '正在取消'
    case 'cancelled':
      return '已取消'
    case 'done':
      return '已完成'
    case 'error':
      return '失败了'
  }
}
