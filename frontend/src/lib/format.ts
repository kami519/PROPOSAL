export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '未知大小'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  if (index === 0) return `${Math.round(value)} ${units[index]}`
  if (value >= 100) return `${value.toFixed(0)} ${units[index]}`
  if (value >= 10) return `${value.toFixed(1)} ${units[index]}`
  return `${value.toFixed(2)} ${units[index]}`
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}

export function heightLabel(height: number | null | undefined): string {
  if (!height || height <= 0) return '未知'
  if (height >= 2160) return '4K'
  if (height >= 1440) return '2K'
  if (height >= 1080) return '1080P'
  if (height >= 720) return '720P'
  if (height >= 480) return '480P'
  if (height >= 360) return '360P'
  return `${height}P`
}

export function secondsToClock(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '未知时长'
  const total = Math.round(seconds)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  return `${minutes}:${String(secs).padStart(2, '0')}`
}

export function isLikelyUrl(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return false
  try {
    const parsed = new URL(/^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

const VIDEO_HOSTS = [
  'bilibili.com',
  'b23.tv',
  'douyin.com',
  'iesdouyin.com',
  'youtube.com',
  'youtu.be',
  'tiktok.com',
  'xiaohongshu.com',
  'xhslink.com',
  'instagram.com',
  'twitter.com',
  'x.com',
  'vimeo.com',
  'kuaishou.com',
  'weibo.com',
  'ixigua.com',
  'music.163.com',
]

// Clipboard text from share sheets often looks like:
// "【标题】 https://b23.tv/xxxx 复制此链接，打开App..."
// Match only ASCII URI characters so the Chinese title/punctuation does not
// become part of the URL.
const URL_IN_TEXT = /https?:\/\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]+/gi
const BARE_URL_IN_TEXT = /(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]*)?/g
const TRAILING_PUNCTUATION = /[.,;:!?'"”’)\]}，。；：！？、）】》」』]+$/u

function cleanCandidate(value: string): string {
  return value
    .replace(/&amp;/g, '&')
    .replace(/^[（(【「]+/u, '')
    .replace(TRAILING_PUNCTUATION, '')
    .trim()
}

function hostMatchesVideoPlatform(value: string): boolean {
  try {
    const host = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`).hostname.toLowerCase()
    return VIDEO_HOSTS.some((known) => host === known || host.endsWith(`.${known}`))
  } catch {
    return false
  }
}

/**
 * Pull the first usable video URL out of arbitrary clipboard / share text.
 * Supports both full `https://...` URLs and bare `b23.tv/...` style links.
 */
export function extractVideoUrl(text: string): string | null {
  if (!text || !text.trim()) return null

  const candidates = new Set<string>()
  for (const match of text.matchAll(URL_IN_TEXT)) {
    const cleaned = cleanCandidate(match[0])
    if (isLikelyUrl(cleaned)) candidates.add(cleaned)
  }
  for (const match of text.matchAll(BARE_URL_IN_TEXT)) {
    const cleaned = cleanCandidate(match[0])
    if (isLikelyUrl(cleaned)) candidates.add(cleaned)
  }

  if (candidates.size === 0) return null
  const all = [...candidates]
  return all.find(hostMatchesVideoPlatform) ?? all[0]
}

export function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value))
}
