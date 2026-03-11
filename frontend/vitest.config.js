import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['public/**/*.spec.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: './coverage',
      include: ['public/**/*.js'],
      exclude: ['public/**/*.spec.js', 'public/**/__tests__/**', 'node_modules/**'],
      thresholds: {
        statements: 40,
        branches: 70,
        functions: 60,
        lines: 40
      }
    }
  }
});
