import type { SummaryResult, SummaryTask, SummaryTaskStatus } from './types'

export const STAGE_LABELS: Record<string, string> = {
  analyzing: '解析视频信息',
  queued: '排队中',
  fetching_subtitles: '提取字幕',
  downloading_audio: '提取音频',
  waiting_transcription: '等待转写',
  transcribing: '语音转写',
  summarizing: '生成总结',
  writing_article: '整理文案',
  done: '完成',
  error: '失败',
  cancelling: '正在取消',
  cancelled: '已取消',
}

export function stageLabel(stage: string | null | undefined): string {
  return (stage && STAGE_LABELS[stage]) || '处理中'
}

export function taskStatusLabel(status: SummaryTaskStatus): string {
  switch (status) {
    case 'analyzing':
      return '解析中'
    case 'queued':
      return '排队中'
    case 'processing':
      return '处理中'
    case 'cancelling':
      return '正在取消'
    case 'cancelled':
      return '已取消'
    case 'done':
      return '已完成'
    case 'error':
      return '失败'
  }
}

export function isTaskActive(
  task: Pick<SummaryTask, 'status' | 'articleStatus'>,
): boolean {
  return (
    task.status === 'queued' ||
    task.status === 'processing' ||
    task.status === 'cancelling' ||
    (task.status === 'done' && task.articleStatus === 'processing')
  )
}

export function markdownFor(result: SummaryResult): string {
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
