import { useEffect, useState } from 'react'
import { Menu, X } from 'lucide-react'
import { useSummaryQueue } from '../context/SummaryQueueContext'
import { BrandMark } from './BrandMark'

const NAV_ITEMS = [
  { href: '#/tasks', label: '任务中心' },
  { href: '#/library', label: '笔记仓库' },
  { href: '#platforms', label: '支持平台' },
  { href: '#faq', label: '常见问题' },
]

export function Header() {
  const { activeCount } = useSummaryQueue()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [menuOpen])

  return (
    <header className="site-header">
      <div className="wrap header-inner">
        <a className="brand" href="#top" aria-label="收片 ClipDock 首页">
          <BrandMark />
          <span>收片</span>
          <span className="brand-en">CLIPDOCK</span>
        </a>

        <nav className="nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
              {item.href === '#/tasks' && activeCount > 0 ? (
                <span className="nav-badge">{activeCount}</span>
              ) : null}
            </a>
          ))}
        </nav>

        <div className="head-actions">
          <span className="engine">
            <i />
            PRIVATE TOOL
          </span>
          <button
            className="menu-btn"
            type="button"
            aria-label={menuOpen ? '关闭菜单' : '打开菜单'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div className="mobile-nav">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>
              {item.label}
              {item.href === '#/tasks' && activeCount > 0 ? (
                <span className="nav-badge">{activeCount}</span>
              ) : null}
            </a>
          ))}
        </div>
      )}
    </header>
  )
}
