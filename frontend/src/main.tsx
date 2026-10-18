import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary.tsx'
import GoApp from './go/GoApp.tsx'
import InsightsApp from './insights/InsightsApp.tsx'

// Two products on one codebase (proposal §9): WalkLah Go for walkers (default) and
// WalkLah Insights for township operators (?app=insights).
const isInsights = new URLSearchParams(window.location.search).get('app') === 'insights'
document.title = isInsights ? 'WalkLah Insights' : 'WalkLah Go'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>{isInsights ? <InsightsApp /> : <GoApp />}</ErrorBoundary>
  </StrictMode>,
)
