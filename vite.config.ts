import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Respect an assigned port (e.g. the preview harness's autoPort) if present.
  server: { port: Number(process.env.PORT) || 5173 },
})
