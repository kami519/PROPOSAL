import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/space-grotesk'
import './index.css'
import './workbench.css'
import './library.css'
import './tasks.css'
import App from './App.tsx'
import { ToastProvider } from './context/ToastContext'
import { SummaryQueueProvider } from './context/SummaryQueueContext'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider>
      <SummaryQueueProvider>
        <App />
      </SummaryQueueProvider>
    </ToastProvider>
  </StrictMode>,
)
