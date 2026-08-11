import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // El dev server reenvía /api al backend, de modo que el navegador ve un
    // único origen y no interviene CORS. En despliegue el estático se sirve
    // tras el mismo reverse proxy que la API, así que la ruta relativa vale.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
