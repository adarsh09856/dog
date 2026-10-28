import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    // Keep the full UI suite below the per-test timeout on developer/CI hosts
    // with many reported CPUs but limited memory bandwidth. High fork counts
    // made module imports contend until otherwise-fast tests timed out.
    maxWorkers: 2,
    // Expose afterEach etc. globally so @testing-library/react auto-registers
    // its DOM cleanup between tests.
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    server: {
      deps: {
        // Inline @stackframe so vi.mock('@stackframe/stack') also intercepts the
        // package's internal imports of its own index (e.g. team-switcher.js
        // importing useUser from '../index.js').
        inline: [/@stackframe/],
      },
    },
  },
});
