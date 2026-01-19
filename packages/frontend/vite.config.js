import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // API target: use VITE_API_URL env var, or default to localhost:3001
  // For LocalStack: set VITE_API_URL to the URL from 'sst deploy --stage local' output
  const apiTarget = env.VITE_API_URL || 'http://localhost:3001'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // For LocalStack API Gateway, paths are different
          ...(apiTarget.includes('4566') && {
            rewrite: (path) => path, // Keep path as-is for LocalStack
          }),
        }
      }
    }
  }
})
