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

export type SummaryStatus = 'queued' | 'processing' | 'done' | 'error'
export type ArticleStatus = 'idle' | 'processing' | 'done' | 'error'

export interface SummaryJob {
  id: string
  status: SummaryStatus
  stage: string
  progress: number
  title: string
  thumbnail: string | null
  platform: string | null
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
  createdAt: number
  updatedAt: number
}

export type LibraryStatus = 'processing' | 'done' | 'error' | 'trashed'

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
}

export type LoadPhase = 'idle' | 'analyzing' | 'ready' | 'downloading' | 'cancelled' | 'done' | 'error'
