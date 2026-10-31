import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // FastAPI runs on :8000 in dev (uvicorn app.main:app --reload)
    proxy: { '/api': 'http://localhost:8000' },
  },
})
