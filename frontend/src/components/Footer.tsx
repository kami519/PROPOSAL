import { BrandMark } from './BrandMark'

export function Footer() {
  return (
    <footer className="site-footer">
      <div className="wrap footer-inner">
        <div className="footer-brand-block">
          <a className="footer-brand" href="#top">
            <BrandMark size={14} />
            收片 <span>CLIPDOCK</span>
          </a>
          <p>自己的视频下载页，简单、直接。</p>
        </div>

        <div className="footer-links">
          <a href="#platforms">支持平台</a>
          <a href="#faq">常见问题</a>
        </div>

        <div className="footer-legal">
          <p>仅用于下载你拥有版权或已获授权的内容。请遵守平台条款。</p>
          <p>不提供 DRM 破解 · 不长期保存视频 · 私人使用</p>
          <p>© 2026 收片 CLIPDOCK</p>
        </div>
      </div>
    </footer>
  )
}
