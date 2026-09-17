import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import net from 'node:net'

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = new net.Socket()
    socket.setTimeout(250)
    socket.on('connect', () => {
      socket.destroy()
      resolve(true)
    })
    socket.on('timeout', () => {
      socket.destroy()
      resolve(false)
    })
    socket.on('error', () => {
      socket.destroy()
      resolve(false)
    })
    socket.connect(port, '127.0.0.1')
  })
}

// https://vite.dev/config/
export default defineConfig(async () => {
  let backendPort = 8000
  if (process.env.BACKEND_PORT) {
    backendPort = Number(process.env.BACKEND_PORT)
  } else {
    // Check whether backend is active on 8000 or 9000
    const is8000 = await checkPort(8000)
    if (is8000) {
      backendPort = 8000
    } else {
      const is9000 = await checkPort(9000)
      if (is9000) {
        backendPort = 9000
      }
    }
  }

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 4000,
      proxy: {
        // Proxy all /api requests to the FastAPI backend during development.
        // This eliminates CORS issues — the browser only sees localhost:4000.
        '/api': {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('error', (err, _req, res) => {
              if (res && !res.headersSent) {
                res.writeHead(503, { 'Content-Type': 'application/json' })
                res.end(
                  JSON.stringify({
                    error: 'BackendServiceUnavailable',
                    detail: `Unable to connect to backend on port ${backendPort}. Ensure uvicorn is running.`,
                  })
                )
              }
            })
          },
        },
      },
    },
  }
})
