// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import sitemap from '@astrojs/sitemap';

// https://astro.build/config
export default defineConfig({
  site: 'https://www.pdx-events.com',
  srcDir: './src-pdx-events',
  integrations: [sitemap()],
  vite: {
    plugins: [tailwindcss()]
  }
});
