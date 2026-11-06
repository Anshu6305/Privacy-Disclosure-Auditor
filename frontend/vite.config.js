import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// During development the SPA runs on 5173 and the API on 8000. Proxying /api
// means the frontend code always calls relative paths, so the same code works
// in development and inside the container, where FastAPI serves both.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  // Tests run in jsdom against a mocked `fetch`. Nothing here reaches a real
  // API: a frontend test that depended on a live backend would pass or fail
  // for reasons that have nothing to do with the component under test.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.jsx'],
    restoreMocks: true,
  },
});
