import { useMemo, useState } from 'react'
import { ListPlus, LoaderCircle } from 'lucide-react'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { useToast } from '../context/ToastContext'
import { extractVideoUrls } from '../lib/format'

const BATCH_LIMIT = 12

export function BatchSummary() {
  const { enqueueUrls } = useSummaryQueue()
  const { pushToast } = useToast()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const urls = useMemo(() => extractVideoUrls(text), [text])

  const start = async () => {
    if (!urls.length || busy) return
    setBusy(true)
    try {
      const result = await enqueueUrls(text)
      const parts = [`已加入 ${result.queued} 个任务`]
      if (result.skipped) parts.push(`跳过 ${result.skipped} 个重复链接`)
      if (result.failed) parts.push(`${result.failed} 个解析失败`)
      if (result.ignored) parts.push(`超出上限忽略 ${result.ignored} 个`)
      pushToast(`${parts.join('，')}。`, result.failed ? 'error' : 'success')
      if (result.queued) setText('')
    } catch (caught) {
      pushToast(
        caught instanceof Error ? caught.message : '批量加入失败，请稍后重试。',
        'error',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="batch-summary">
      <div className="batch-summary-head">
        <div>
          <div className="batch-kicker">BATCH / 批量总结</div>
          <h2>一次粘贴多个视频，后台并行处理。</h2>
          <p>每行一个链接，也可以直接粘贴整段分享文字；最多一次 {BATCH_LIMIT} 条。</p>
        </div>
        <span className="batch-count">
          {urls.length ? `识别到 ${urls.length} 个链接` : '等待粘贴'}
        </span>
      </div>

      <label className="sr-only" htmlFor="batch-summary-urls">
        批量视频链接
      </label>
      <textarea
        id="batch-summary-urls"
        className="batch-input"
        rows={3}
        value={text}
        onChange={(event) => setText(event.target.value)}
        placeholder={'https://www.bilibili.com/video/BV...\nhttps://www.bilibili.com/video/BV...\n也可以直接粘贴多段分享文字'}
        spellCheck={false}
        disabled={busy}
      />

      <div className="batch-actions">
        <span className="batch-hint">
          {urls.length > BATCH_LIMIT
            ? `超过 ${BATCH_LIMIT} 条，只会处理前 ${BATCH_LIMIT} 条`
            : '解析完一条就入队一条，入队后可以关闭页面'}
        </span>
        <button
          className="go-btn batch-submit"
          type="button"
          onClick={() => void start()}
          disabled={busy || !urls.length}
        >
          {busy ? (
            <>
              <LoaderCircle className="spin" size={15} />
              正在加入
            </>
          ) : (
            <>
              <ListPlus size={15} />
              加入并行队列
            </>
          )}
        </button>
      </div>
    </section>
  )
}
