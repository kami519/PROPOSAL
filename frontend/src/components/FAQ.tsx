import { ChevronDown } from 'lucide-react'

const FAQS = [
  {
    question: '为什么有些链接解析失败？',
    answer:
      '常见原因是平台要求登录、地区限制、DRM 版权保护、直播/预告，或者视频本身已删除。YouTube 这类平台还可能触发机器人验证。可以先换一个公开链接再试。',
  },
  {
    question: '网站会保存我下载的视频吗？',
    answer:
      '不会长期保存。服务器只做临时中转，文件默认 30 分钟后自动清理，不建立视频库，也不需要你注册账号。',
  },
  {
    question: '支持哪些平台？',
    answer:
      '解析能力覆盖超过 1,800 个站点。B站、抖音、X、TikTok 等通常可用；YouTube、Instagram、Vimeo 可能因登录或风控失败。页面上的平台列表不是成功承诺。',
  },
  {
    question: '手机上怎么用？',
    answer:
      '直接用手机浏览器打开本站即可。粘贴链接、选画质、点下载，文件会进入浏览器的下载列表。部署到公网后随时随地都能用；本地演示时，手机和电脑需要在同一局域网。',
  },
  {
    question: '“粘贴”按钮没反应，或剪贴板里是中文怎么办？',
    answer:
      '现在会自动从整段分享文字中提取视频链接，标题、表情和“复制此链接”之类的文字都不会影响解析。如果通过局域网 HTTP 地址访问，浏览器会禁止网页一键读取剪贴板，请长按输入框手动粘贴，或改用 localhost / HTTPS。手动粘贴整段分享文字后直接点“开始收片”也可以。',
  },
  {
    question: '为什么视频标着 4K，页面只能下 1080P？',
    answer:
      '有些平台会把 4K、HDR 或高帧率作为登录/会员权益。当前服务端没有对应权限时，平台只会返回 1080P 文件，页面会在画质区提示缺失的清晰度。这不是把 4K 压成了 1080P，而是源站没有把 4K 文件开放给当前请求。',
  },
  {
    question: 'AI 总结需要什么？',
    answer:
      '需要在服务端配置一个 OpenAI 兼容的模型 Key。没有字幕的视频会用本地 Whisper 转写，首次使用会下载模型，长视频在 CPU 上会慢一些。',
  },
  {
    question: '下载内容有版权风险吗？',
    answer:
      '请只下载你拥有版权、已获授权，或平台明确允许保存的内容。不要用本站下载付费课程、私密视频或受 DRM 保护的内容。公开运营还需要自行评估平台条款和当地法律。',
  },
]

export function FAQ() {
  return (
    <section className="section faq-section" id="faq">
      <div className="section-head">
        <div>
          <div className="section-kicker">FAQ / 先把丑话说前面</div>
          <h2 className="section-title">
            能下什么，
            <br />
            不能下<span className="accent">什么</span>。
          </h2>
        </div>
        <p className="section-note">不承诺“100% 万能”。把限制讲清楚，比失败后让你猜更好。</p>
      </div>
      <div className="faq-list">
        {FAQS.map((item, index) => (
          <details className="faq-item" key={item.question} open={index === 0}>
            <summary>
              <span>{item.question}</span>
              <ChevronDown size={18} className="faq-chevron" />
            </summary>
            <p>{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  )
}
