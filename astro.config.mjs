// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import rehypeFractions from './src/plugins/rehype-fractions.mjs';

// https://astro.build/config
export default defineConfig({
  markdown: {
    rehypePlugins: [rehypeFractions],
  },
  vite: {
    plugins: [tailwindcss()]
  }
});
