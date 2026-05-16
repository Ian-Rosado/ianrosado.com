// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import rehypeFractions from './src/plugins/rehype-fractions.mjs';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  site: 'https://www.ianrosado.com',
  integrations: [sitemap()],
  markdown: {
    rehypePlugins: [rehypeFractions],
  },
  vite: {
    plugins: [tailwindcss()]
  }
});
