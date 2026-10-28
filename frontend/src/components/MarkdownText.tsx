import type { ReactNode } from 'react'

/**
 * A deliberately small Markdown renderer for the AI 整理稿.
 *
 * We only need headings, paragraphs, lists, quotes, code and inline emphasis.
 * Rendering to React nodes (instead of raw HTML) keeps the output safe without
 * pulling in a full Markdown + sanitizer stack.
 */

const INLINE_RE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let index = 0
  for (const match of text.matchAll(INLINE_RE)) {
    const start = match.index ?? 0
    if (start > last) nodes.push(text.slice(last, start))
    const token = match[0]
    const key = `${keyPrefix}-${index++}`
    if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(<strong key={key}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(<code key={key}>{token.slice(1, -1)}</code>)
    } else {
      const link = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(token)
      if (link) {
        nodes.push(
          <a key={key} href={link[2]} target="_blank" rel="noopener noreferrer">
            {link[1]}
          </a>,
        )
      } else {
        nodes.push(token)
      }
    }
    last = start + token.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

function isBlockStart(line: string): boolean {
  return (
    /^#{1,4}\s+/.test(line) ||
    /^```/.test(line) ||
    /^>\s?/.test(line) ||
    /^\s*[-*]\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line) ||
    /^\s*---+\s*$/.test(line)
  )
}

function parseBlocks(source: string): ReactNode[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }

    if (/^```/.test(line)) {
      const lang = line.slice(3).trim()
      const body: string[] = []
      index += 1
      while (index < lines.length && !/^```/.test(lines[index])) {
        body.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push(
        <pre className="md-code-block" key={`code-${index}`}>
          <code data-lang={lang || undefined}>{body.join('\n')}</code>
        </pre>,
      )
      continue
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line)
    if (heading) {
      const level = Math.min(4, heading[1].length)
      const content = renderInline(heading[2], `h-${index}`)
      if (level === 1) blocks.push(<h1 key={`h-${index}`}>{content}</h1>)
      else if (level === 2) blocks.push(<h2 key={`h-${index}`}>{content}</h2>)
      else if (level === 3) blocks.push(<h3 key={`h-${index}`}>{content}</h3>)
      else blocks.push(<h4 key={`h-${index}`}>{content}</h4>)
      index += 1
      continue
    }

    if (/^>\s?/.test(line)) {
      const body: string[] = []
      while (index < lines.length && /^>\s?/.test(lines[index])) {
        body.push(lines[index].replace(/^>\s?/, ''))
        index += 1
      }
      blocks.push(
        <blockquote key={`quote-${index}`}>
          {renderInline(body.join(' '), `quote-${index}`)}
        </blockquote>,
      )
      continue
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ''))
        index += 1
      }
      blocks.push(
        <ul key={`ul-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`li-${index}-${itemIndex}`}>
              {renderInline(item, `li-${index}-${itemIndex}`)}
            </li>
          ))}
        </ul>,
      )
      continue
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ''))
        index += 1
      }
      blocks.push(
        <ol key={`ol-${index}`}>
          {items.map((item, itemIndex) => (
            <li key={`oli-${index}-${itemIndex}`}>
              {renderInline(item, `oli-${index}-${itemIndex}`)}
            </li>
          ))}
        </ol>,
      )
      continue
    }

    if (/^\s*---+\s*$/.test(line)) {
      blocks.push(<hr key={`hr-${index}`} />)
      index += 1
      continue
    }

    const paragraph: string[] = [line]
    index += 1
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines[index])) {
      paragraph.push(lines[index])
      index += 1
    }
    blocks.push(
      <p key={`p-${index}`}>{renderInline(paragraph.join(' '), `p-${index}`)}</p>,
    )
  }

  return blocks
}

export function MarkdownText({
  source,
  className = '',
}: {
  source: string
  className?: string
}) {
  const cleaned = source.replace(/<!--[\s\S]*?-->/g, '')
  return <div className={`md-body ${className}`.trim()}>{parseBlocks(cleaned)}</div>
}
