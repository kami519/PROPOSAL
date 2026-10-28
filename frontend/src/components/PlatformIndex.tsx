const PLATFORM_ROWS = [
  { name: 'B站', category: '视频社区', status: '稳定支持', tone: 'ok' },
  { name: '抖音', category: '短视频', status: '多数可用', tone: 'ok' },
  { name: 'YouTube', category: '海外视频', status: '可能需 Cookies', tone: 'warn' },
  { name: 'TikTok', category: '短视频', status: '以实际为准', tone: 'warn' },
  { name: '小红书', category: '生活社区', status: '部分可用', tone: 'warn' },
  { name: 'X', category: '社交视频', status: '多数可用', tone: 'ok' },
  { name: 'Instagram', category: '社交视频', status: '可能需登录', tone: 'warn' },
  { name: 'Vimeo', category: '海外视频', status: '可能需登录', tone: 'warn' },
  { name: '快手', category: '短视频', status: '以实际为准', tone: 'warn' },
  { name: '西瓜视频', category: '视频社区', status: '以实际为准', tone: 'warn' },
  { name: '微博', category: '社交视频', status: '以实际为准', tone: 'warn' },
  { name: '网易云音乐', category: '音乐 / 播客', status: '以实际为准', tone: 'warn' },
]

export function PlatformIndex() {
  return (
    <section className="section platform-section" id="platforms">
      <div className="section-head">
        <div>
          <div className="section-kicker">SUPPORTED SITES / 平台索引</div>
          <h2 className="section-title">
            一个入口，
            <br />
            收下<span className="accent">各个平台</span>。
          </h2>
        </div>
        <p className="section-note">
          平台风控、登录要求、地区限制和 DRM 都可能让某条链接失败，实际以解析结果为准。
        </p>
      </div>

      <div className="platform-grid">
        {PLATFORM_ROWS.map((platform, index) => (
          <div className="platform-card" key={platform.name}>
            <span className="platform-index">{String(index + 1).padStart(2, '0')}</span>
            <div className="platform-main">
              <strong>{platform.name}</strong>
              <span>{platform.category}</span>
            </div>
            <span className={`platform-status ${platform.tone}`}>
              <i />
              {platform.status}
            </span>
          </div>
        ))}
      </div>

      <div className="platform-foot">
        <span>1,800+ 站点持续更新</span>
        <span>列表不是承诺，失败时请换一个公开链接再试</span>
        <a href="#faq">遇到失败怎么办？</a>
      </div>
    </section>
  )
}
