// @ts-check
import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';
import sitemap from '@astrojs/sitemap';

// Sitemap <lastmod>: the event pages are rebuilt from the calendars on every
// deploy, so they change each build; a dated /picks/ page is fixed once its
// week starts; static pages get none (Google ignores lastmod it can't trust).
const BUILD_TIME = new Date().toISOString();
const STATIC_PAGE = /\/(about|favorites|pickup-soccer|subscribe)\/$/;
function lastmod(item) {
  const picks = item.url.match(/\/picks\/(?:week|weekend)-of-(\d{4}-\d{2}-\d{2})\/$/);
  if (picks) item.lastmod = picks[1];
  else if (!STATIC_PAGE.test(item.url)) item.lastmod = BUILD_TIME;
  return item;
}

// https://astro.build/config
export default defineConfig({
  site: 'https://www.pdx-events.com',
  srcDir: './src-pdx-events',
  publicDir: './public-pdx-events',
  integrations: [sitemap({ serialize: lastmod })],
  vite: {
    plugins: [tailwindcss()]
  }
});
