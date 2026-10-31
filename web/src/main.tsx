import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'
import { routes } from './routes.tsx'

try { if (localStorage.getItem('theme') === 'light') document.documentElement.dataset.theme = 'light' } catch { /* storage blocked */ }

const queryClient = new QueryClient()
const router = createBrowserRouter(routes, { basename: '/app' })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
