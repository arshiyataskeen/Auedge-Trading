import { defineConfig } from '@playwright/test'

// e2e runs against the live server (python -m uvicorn app:app --port 8000) serving the built app at /app/
export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://127.0.0.1:8000' },
})
