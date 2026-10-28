export type FormatId = '720p' | '1080p' | 'best' | 'audio'

export interface FormatOption {
  id: FormatId | string
  label: string
  sublabel: string
  height: number | null
  ext: string
  size: number | null
  sizeText: string | null
  kind: 'video' | 'audio'
}

export interface QualityNotice {
  code: string
  message: string
  missingFormats: string[]
  maxAvailableHeight: number | null
}

export interface AnalyzeResult {
  title: string
  uploader: string
  duration: number
  durationText: string
  thumbnail: string | null
  webpageUrl: string
  platform: string
  sourceHeight: number | null
  formats: FormatOption[]
  qualityNotice?: QualityNotice | null
}

export type JobStatus =
  | 'queued'
  | 'downloading'
  | 'pausing'
  | 'paused'
  | 'processing'
  | 'cancelling'
  | 'cancelled'
  | 'done'
  | 'error'

export interface Job {
  id: string
  status: JobStatus
  progress: number
  downloadedBytes: number
  totalBytes: number | null
  speed: string | null
  eta: string | null
  title: string
  thumbnail: string | null
  platform: string | null
  format: string
  filename: string | null
  filesize: number | null
  downloadUrl: string | null
  error: string | null
  errorCode: string | null
  canPause: boolean
  canResume: boolean
  canCancel: boolean
  createdAt: number
  updatedAt: number
}

export interface SummaryChapter {
  time: string
  title: string
  summary: string
}

export interface SummaryResult {
  tldr: string
  keyPoints: string[]
  chapters: SummaryChapter[]
  quotes: string[]
  keywords: string[]
  suitableFor?: string
  totalKeyPoints?: number
  totalChapters?: number
  model?: string
  generatedAt?: number
  fallback?: boolean
}

export type SummaryStatus =
  | 'queued'
  | 'processing'
  | 'cancelling'
  | 'cancelled'
  | 'done'
  | 'error'
export type ArticleStatus = 'idle' | 'processing' | 'done' | 'error' | 'cancelled'

export interface SummaryJob {
  id: string
  url?: string
  status: SummaryStatus
  stage: string
  progress: number
  title: string
  thumbnail: string | null
  platform: string | null
  uploader?: string | null
  duration: number
  transcriptSource: 'subtitle' | 'audio' | null
  transcriptAvailable?: boolean
  transcriptChars?: number
  result: SummaryResult | null
  articleStatus?: ArticleStatus
  articleProgress?: number
  articleChars?: number
  articleError?: string | null
  noteId?: string | null
  error: string | null
  errorCode: string | null
  queuePosition?: number
  transcribeQueuePosition?: number
  canCancel?: boolean
  canRetry?: boolean
  deduped?: boolean
  hasResult?: boolean
  tldr?: string
  retryCount?: number
  startedAt?: number | null
  finishedAt?: number | null
  createdAt: number
  updatedAt: number
}

export type SummaryTaskStatus = 'analyzing' | SummaryStatus

export interface SummaryTask extends Omit<SummaryJob, 'status'> {
  status: SummaryTaskStatus
  url: string
  addedAt?: number
  localError?: string | null
}

export interface SummaryListResponse {
  items: SummaryJob[]
  active: number
  queued: number
  maxActive: number
  maxQueue: number
}

export type LibraryStatus = 'processing' | 'done' | 'error' | 'cancelled' | 'trashed'

export interface LibraryNote {
  id: string
  title: string
  aiSummary: string
  sourceUrl: string
  platform: string
  uploader: string
  duration: number
  durationText: string
  status: LibraryStatus
  transcriptSource: string
  model: string
  createdAt: string
  updatedAt: string
  fileSize: number
  error: string
  fileName: string
  filePath: string
  trashed: boolean
}

export interface LibraryList {
  items: LibraryNote[]
  total: number
  page: number
  pageSize: number
}

export interface TranscriptPayload {
  id: string
  source: string | null
  chars: number
  transcript: string
}

export interface ArticlePayload {
  id: string
  status: ArticleStatus
  progress: number
  article: string | null
  chars: number
  error: string | null
}

export interface Health {
  ok: boolean
  name: string
  version: string
  ytDlpVersion: string
  ffmpeg: string
  freeBytes: number
  jobs: number
  cookiesConfigured: boolean
  summaryConfigured: boolean
  summaryModel?: string
  articleEnabled?: boolean
  whisperAvailable: boolean
  summaryActive?: number
  summaryWorkers?: number
  transcribeWorkers?: number
  llmConcurrency?: number
}

export type LoadPhase = 'idle' | 'analyzing' | 'ready' | 'downloading' | 'cancelled' | 'done' | 'error'
