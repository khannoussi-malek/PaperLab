import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { queryClient } from './api/queries'
import App from './App.tsx'
import { ThemeProvider } from './components/theme-provider'
import { warmPlotlyAtChartLink } from './features/charts/loadPlotly'
import './index.css'

// Plotly loads on first use; a pointer or focus on a chart link starts it early, so the chart doesn't wait for it.
document.addEventListener('pointerover', warmPlotlyAtChartLink)
document.addEventListener('focusin', warmPlotlyAtChartLink)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <App />
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
