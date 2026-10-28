import { defineConfig } from 'vitest/config';
export default defineConfig({test:{include:['tests/unit/**/*.test.mjs'],testTimeout:30000,passWithNoTests:false}});

