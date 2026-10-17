import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The backend's CORS only allows http://localhost:5173 and http://127.0.0.1:5173,
// so the dev server must never silently move to another port.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  preview: { port: 5173, strictPort: true },
  // MapLibre GL alone is ~800 kB minified; that is expected for a map app.
  build: { chunkSizeWarningLimit: 1200 },
})
