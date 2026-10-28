import { Play } from 'lucide-react'

export function HeroVisual() {
  return (
    <div className="hero-visual" aria-hidden="true">
      <div className="orbit-label">NO APP · NO LOGIN · JUST DROP IT</div>

      <div className="receipt-back">
        <div>
          <div className="mono">CLIPDOCK RECEIPT / #A19F</div>
          <div className="receipt-big">
            已收片。
            <br />
            存在你的
            <br />
            相册里。
          </div>
        </div>
        <div>
          <div className="barcode" />
          <div className="receipt-row">
            <span>FILE</span>
            <span>city_night_4k.mp4</span>
          </div>
          <div className="receipt-row receipt-row-tight">
            <span>STATUS</span>
            <span>DELIVERED 00:03</span>
          </div>
        </div>
      </div>

      <div className="parcel">
        <div className="parcel-head">
          <span>LIVE PARCEL / 正在收片</span>
          <span className="live">DOWNLOADING</span>
        </div>
        <div className="parcel-thumb">
          <div className="parcel-grain" />
          <span className="play-badge">
            <Play size={20} fill="currentColor" strokeWidth={0} />
          </span>
          <span className="quality-badge">1080P · MP4</span>
          <span className="duration-badge">00:03:32</span>
        </div>
        <div className="video-meta">
          <div className="video-title">
            <span>城市夜景延时 · 4K 修复版</span>
            <span>B站</span>
          </div>
          <div className="video-sub">
            <span>@framelab</span>
            <span>·</span>
            <span>1.2 GB</span>
            <span>·</span>
            <span>已识别</span>
          </div>
        </div>
        <div className="progress-wrap">
          <div className="progress-top">
            <span>正在下载 · 视频 + 音频</span>
            <b>68%</b>
          </div>
          <div className="bar">
            <i />
          </div>
        </div>
        <div className="parcel-bottom">
          <div className="format-pill">
            <b>MP4</b>
            <span>4.2 MB/s · 还剩 00:18</span>
          </div>
          <span className="auto-save">自动保存 ↓</span>
        </div>
      </div>

      <div className="done-ticket">
        <b>已存入相册</b>
        <span>1 个文件 · 38.4 MB</span>
      </div>
    </div>
  )
}
