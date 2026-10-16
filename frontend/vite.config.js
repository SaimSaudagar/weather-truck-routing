import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      // maplibre is most of the bundle and rarely changes, cache it separately
      output: { manualChunks: { maplibre: ['maplibre-gl'] } },
    },
    chunkSizeWarningLimit: 900,
  },
  server: {
    // in dev the API runs on :8000, so proxy instead of fighting CORS
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
