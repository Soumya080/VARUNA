import path from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: {
      // `__dirname` doesn't exist in a real ESM module (this file is
      // `.mts`); `import.meta.dirname` is its native replacement (Node
      // 20.11+) — fixes the vite config-loader deprecation warning.
      '@': path.resolve(import.meta.dirname, '.'),
    },
  },
  test: {
    environment: 'node',
  },
})
