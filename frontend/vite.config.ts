import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Quick tunnels (trycloudflare.com) use a random Host header; allow them in dev.
    allowedHosts: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
