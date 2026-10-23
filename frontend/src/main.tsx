import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import GoApp from './go/GoApp.tsx'
import InsightsApp from './insights/InsightsApp.tsx'

// One app, two views (proposal §9): the walker view (default) and the township
// operator view (?app=insights).
const isInsights = new URLSearchParams(window.location.search).get('app') === 'insights'
document.title = 'WalkLah'

// Installable app: the service worker caches only the app shell (production builds only,
// so development always loads fresh code).
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>{isInsights ? <InsightsApp /> : <GoApp />}</ErrorBoundary>
  </StrictMode>,
)
