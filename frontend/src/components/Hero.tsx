import { useState } from 'react'
import { Downloader } from './Downloader'
import { HeroVisual } from './HeroVisual'

export function Hero() {
  const [hasResult, setHasResult] = useState(false)

  return (
    <section className={`hero ${hasResult ? 'has-result' : ''}`}>
      <div className="hero-copy">
        <div className="eyebrow">
          <span className="eyebrow-tag">PRIVATE</span>
          自己的视频下载页
        </div>
        <h1>
          <span className="line">视频，</span>
          <span className="line">
            <span className="mark">直接收进</span>本地。
          </span>
        </h1>
        <p className="sub">
          粘贴链接，选清晰度，直接下载。
          <strong>B站、抖音、YouTube、TikTok</strong> 都支持。
        </p>
        <Downloader onResultChange={setHasResult} />
      </div>
      {hasResult ? null : <HeroVisual />}
    </section>
  )
}
