import { useEffect, useState } from 'react'
import { FAQ } from './components/FAQ'
import { Footer } from './components/Footer'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { PlatformIndex } from './components/PlatformIndex'
import { LibraryPage } from './pages/LibraryPage'
import { TaskCenterPage } from './pages/TaskCenterPage'
import { TaskDetailPage } from './pages/TaskDetailPage'

type Route =
  | { view: 'home' }
  | { view: 'library'; noteId?: string }
  | { view: 'tasks'; taskId?: string }

function readRoute(): Route {
  const hash = window.location.hash || ''
  const tasksMatch = /^#\/tasks(?:\/([^/?]+))?/.exec(hash)
  if (tasksMatch) return { view: 'tasks', taskId: tasksMatch[1] }
  const match = /^#\/library(?:\/([^/?]+))?/.exec(hash)
  if (match) return { view: 'library', noteId: match[1] }
  return { view: 'home' }
}

export default function App() {
  const [route, setRoute] = useState<Route>(readRoute)

  useEffect(() => {
    const onHashChange = () => {
      setRoute(readRoute())
      window.scrollTo({ top: 0, behavior: 'auto' })
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  if (route.view === 'tasks') {
    return (
      <div className="page tasks-shell" id="top">
        <a className="skip-link" href="#tasks-main">
          跳到任务中心
        </a>
        <div className="noise" aria-hidden="true" />
        <Header />
        <main id="tasks-main">
          {route.taskId ? (
            <TaskDetailPage taskId={route.taskId} />
          ) : (
            <TaskCenterPage />
          )}
        </main>
        <Footer />
      </div>
    )
  }

  if (route.view === 'library') {
    return (
      <div className="page library-shell" id="top">
        <a className="skip-link" href="#library-main">
          跳到笔记仓库
        </a>
        <div className="noise" aria-hidden="true" />
        <Header />
        <main id="library-main">
          <LibraryPage initialNoteId={route.noteId} />
        </main>
        <Footer />
      </div>
    )
  }

  return (
    <div className="page" id="top">
      <a className="skip-link" href="#video-url">
        跳到下载框
      </a>
      <div className="noise" aria-hidden="true" />
      <Header />
      <main>
        <div className="wrap">
          <Hero />
          <PlatformIndex />
          <FAQ />
        </div>
      </main>
      <Footer />
    </div>
  )
}
