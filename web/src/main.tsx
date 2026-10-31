import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

try { if (localStorage.getItem('theme') === 'light') document.documentElement.dataset.theme = 'light' } catch { /* storage blocked */ }

const queryClient = new QueryClient()
const router = createBrowserRouter(
  [{ path: '/', element: <App />, children: [{ index: true, element: <div className="p-4 text-strong">AuEdge</div> }] }],
  { basename: '/app' },
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
